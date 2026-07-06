package com.copyas.burp;

import burp.api.montoya.BurpExtension;
import burp.api.montoya.MontoyaApi;
import burp.api.montoya.core.ToolType;
import burp.api.montoya.http.HttpService;
import burp.api.montoya.http.message.HttpHeader;
import burp.api.montoya.http.message.HttpRequestResponse;
import burp.api.montoya.http.message.requests.HttpRequest;
import burp.api.montoya.ui.contextmenu.ContextMenuEvent;
import burp.api.montoya.ui.contextmenu.ContextMenuItemsProvider;
import burp.api.montoya.ui.contextmenu.MessageEditorHttpRequestResponse;
import burp.api.montoya.ui.menu.MenuItem;

import javax.swing.JMenuItem;
import java.awt.Component;
import java.awt.Toolkit;
import java.awt.datatransfer.StringSelection;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

public class CopyAsExtension implements BurpExtension, ContextMenuItemsProvider {

    private MontoyaApi api;

    @Override
    public void initialize(MontoyaApi api) {
        this.api = api;
        api.extension().setName("CopyAs");
        api.userInterface().registerContextMenuItemsProvider(this);
        api.logging().logToOutput("[*] CopyAs loaded");
    }

    @Override
    public List<Component> provideMenuItems(ContextMenuEvent event) {
        Optional<HttpRequestResponse> selected = selectedRequestResponse(event);
        if (selected.isEmpty()) {
            return Collections.emptyList();
        }

        RequestData data = parse(selected.get());
        if (data == null) {
            return Collections.emptyList();
        }

        List<Component> items = new ArrayList<>();
        for (Format format : Format.values()) {
            items.add(buildSwingMenuItem(format.getLabel(), () -> copy(format.generate(data))));
        }
        return items;
    }

    private static JMenuItem buildSwingMenuItem(String label, Runnable action) {
        JMenuItem mi = new JMenuItem(label);
        mi.addActionListener(e -> action.run());
        return mi;
    }

    private Optional<HttpRequestResponse> selectedRequestResponse(ContextMenuEvent event) {
        if (event.isFromTool(ToolType.PROXY, ToolType.TARGET, ToolType.INTRUDER, ToolType.REPEATER, ToolType.LOGGER)) {
            if (!event.selectedRequestResponses().isEmpty()) {
                return Optional.of(event.selectedRequestResponses().get(0));
            }
        }
        Optional<MessageEditorHttpRequestResponse> me = event.messageEditorRequestResponse();
        if (me.isPresent()) {
            return Optional.of(me.get().requestResponse());
        }
        return Optional.empty();
    }

    private RequestData parse(HttpRequestResponse rr) {
        if (rr == null || rr.request() == null) {
            return null;
        }
        HttpRequest req = rr.request();
        HttpService svc = req.httpService();

        List<HttpHeader> headerList = req.headers();
        String method = req.method();
        String path = req.path();
        if (path == null || path.isEmpty()) {
            path = "/";
        }

        boolean isHttps = svc != null && svc.secure();
        String protocol = isHttps ? "https" : "http";
        String host = svc != null ? svc.host() : "";
        int port = svc != null ? svc.port() : (isHttps ? 443 : 80);

        String url;
        if ((isHttps && port == 443) || (!isHttps && port == 80)) {
            url = protocol + "://" + host + path;
        } else {
            url = protocol + "://" + host + ":" + port + path;
        }

        Map<String, String> headers = new TreeMap<>();
        Map<String, String> cookies = new TreeMap<>();
        String contentType = "";

        for (HttpHeader h : headerList) {
            String name = h.name();
            String value = h.value();
            if (name.equalsIgnoreCase("Cookie")) {
                for (String part : value.split(";")) {
                    String trimmed = part.trim();
                    int eq = trimmed.indexOf('=');
                    if (eq > 0) {
                        cookies.put(trimmed.substring(0, eq).trim(), trimmed.substring(eq + 1).trim());
                    }
                }
            } else if (name.equalsIgnoreCase("Host") || name.equalsIgnoreCase("Content-Length")) {
                continue;
            } else {
                if (name.equalsIgnoreCase("Content-Type")) {
                    contentType = value;
                }
                headers.put(name, value);
            }
        }

        String body = req.bodyToString();
        return new RequestData(method, url, headers, cookies, body == null ? "" : body, contentType);
    }

    private static void copy(String text) {
        StringSelection sel = new StringSelection(text);
        Toolkit.getDefaultToolkit().getSystemClipboard().setContents(sel, null);
    }

    // --- Format enum dispatch --------------------------------------------------

    private enum Format {
        PYTHON("Python (requests)", CopyAsExtension::python),
        GO("Go (net/http)", CopyAsExtension::go),
        CURL("cURL", CopyAsExtension::curl),
        FETCH("JavaScript (fetch)", CopyAsExtension::fetch),
        AXIOS("JavaScript (axios)", CopyAsExtension::axios),
        PHP("PHP (curl)", CopyAsExtension::php),
        RUBY("Ruby (net/http)", CopyAsExtension::ruby),
        CSHARP("C# (HttpClient)", CopyAsExtension::csharp),
        JAVA("Java (HttpClient)", CopyAsExtension::java),
        POWERSHELL("PowerShell", CopyAsExtension::powershell),
        RUST("Rust (reqwest)", CopyAsExtension::rust),
        WGET("wget", CopyAsExtension::wget);

        private final String label;
        private final Generator gen;

        Format(String label, Generator gen) {
            this.label = label;
            this.gen = gen;
        }

        String getLabel() {
            return label;
        }

        String generate(RequestData d) {
            return gen.generate(d);
        }
    }

    @FunctionalInterface
    private interface Generator {
        String generate(RequestData d);
    }

    // --- RequestData ---------------------------------------------------------

    private static class RequestData {
        final String method;
        final String url;
        final Map<String, String> headers;
        final Map<String, String> cookies;
        final String body;
        final String contentType;

        RequestData(String method, String url, Map<String, String> headers,
                    Map<String, String> cookies, String body, String contentType) {
            this.method = method;
            this.url = url;
            this.headers = headers;
            this.cookies = cookies;
            this.body = body;
            this.contentType = contentType;
        }

        boolean hasJsonBody() {
            return body != null && !body.isEmpty() && contentType != null && contentType.toLowerCase().contains("json");
        }
    }

    // --- Generators -----------------------------------------------------------

    private static String python(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("import requests\n\n");
        sb.append("url = \"").append(escPy(d.url)).append("\"\n");

        if (!d.headers.isEmpty()) {
            sb.append("\nheaders = {\n");
            for (Map.Entry<String, String> e : d.headers.entrySet()) {
                sb.append("    \"").append(escPy(e.getKey())).append("\": \"").append(escPy(e.getValue())).append("\",\n");
            }
            sb.append("}\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("\ncookies = {\n");
            for (Map.Entry<String, String> e : d.cookies.entrySet()) {
                sb.append("    \"").append(escPy(e.getKey())).append("\": \"").append(escPy(e.getValue())).append("\",\n");
            }
            sb.append("}\n");
        }

        String bodyArg = "";
        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                String jsonStr = jsonToPython(d.body);
                if (jsonStr != null) {
                    sb.append("\njson_body = ").append(jsonStr).append("\n");
                    bodyArg = ", json=json_body";
                } else {
                    sb.append("\ndata = '").append(escPy(d.body)).append("'\n");
                    bodyArg = ", data=data";
                }
            } else {
                sb.append("\ndata = '").append(escPy(d.body)).append("'\n");
                bodyArg = ", data=data";
            }
        }

        String method = d.method.toLowerCase();
        String call;
        String[] valid = {"get", "post", "put", "patch", "delete", "head", "options"};
        boolean found = false;
        for (String m : valid) {
            if (m.equals(method)) { found = true; break; }
        }
        if (found) {
            call = "requests." + method + "(url";
        } else {
            call = "requests.request('" + d.method + "', url";
        }

        List<String> kwargs = new ArrayList<>();
        if (!d.headers.isEmpty()) kwargs.add("headers=headers");
        if (!d.cookies.isEmpty()) kwargs.add("cookies=cookies");
        if (!bodyArg.isEmpty()) kwargs.add(bodyArg.substring(2));

        sb.append("\nresponse = ").append(call);
        if (!kwargs.isEmpty()) sb.append(", ").append(String.join(", ", kwargs));
        sb.append(")\n\nprint(response.status_code)\nprint(response.text)\n");
        return sb.toString();
    }

    private static String jsonToPython(String body) {
        try {
            Object parsed = MiniJson.parse(body);
            if (parsed == null) return null;
            return MiniJson.toPythonLiteral(parsed, 0);
        } catch (Exception e) {
            return null;
        }
    }

    private static String go(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("package main\n\n");
        sb.append("import (\n");
        sb.append("\t\"fmt\"\n");
        sb.append("\t\"io\"\n");
        sb.append("\t\"net/http\"\n");
        sb.append("\t\"strings\"\n");
        sb.append(")\n\n");
        sb.append("func main() {\n");

        boolean hasBody = !d.body.isEmpty();
        if (hasBody) {
            sb.append("\tbody := strings.NewReader(").append(escGoRawString(d.body)).append(")\n");
        }
        sb.append("\treq, _ := http.NewRequest(\"").append(d.method).append("\", \"").append(escDq(d.url)).append("\", ")
                .append(hasBody ? "body" : "nil").append(")\n");

        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append("\treq.Header.Set(\"").append(escDq(e.getKey())).append("\", \"").append(escDq(e.getValue())).append("\")\n");
        }
        for (Map.Entry<String, String> e : d.cookies.entrySet()) {
            sb.append("\treq.AddCookie(&http.Cookie{Name: \"").append(escDq(e.getKey()))
                    .append("\", Value: \"").append(escDq(e.getValue())).append("\"})\n");
        }

        sb.append("\n\tresp, _ := http.DefaultClient.Do(req)\n");
        sb.append("\tdefer resp.Body.Close()\n\n");
        sb.append("\tdata, _ := io.ReadAll(resp.Body)\n");
        sb.append("\tfmt.Println(resp.StatusCode)\n");
        sb.append("\tfmt.Println(string(data))\n");
        sb.append("}\n");
        return sb.toString();
    }

    private static String curl(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("curl -s -X ").append(d.method).append(" \"").append(escDq(d.url)).append("\"");
        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append(" \\\n  -H \"").append(e.getKey()).append(": ").append(escDq(e.getValue())).append("\"");
        }
        if (!d.cookies.isEmpty()) {
            sb.append(" \\\n  -H \"Cookie: ").append(joinCookies(d.cookies)).append("\"");
        }
        if (!d.body.isEmpty()) {
            sb.append(" \\\n  --data-raw ").append(escShellSingleQuote(d.body));
        }
        return sb.toString();
    }

    private static String fetch(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("const response = await fetch(\"").append(escJs(d.url)).append("\", {\n");
        sb.append("  method: \"").append(d.method).append("\",\n");

        if (!d.headers.isEmpty()) {
            sb.append("  headers: {\n");
            for (Map.Entry<String, String> e : d.headers.entrySet()) {
                sb.append("    \"").append(escJs(e.getKey())).append("\": \"").append(escJs(e.getValue())).append("\",\n");
            }
            sb.append("  },\n");
        }

        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("  body: JSON.stringify(").append(d.body).append("),\n");
            } else {
                sb.append("  body: ").append(escJsTemplateLiteral(d.body)).append(",\n");
            }
        }

        sb.append("});\n\nconsole.log(response.status);\nconsole.log(await response.text());\n");
        return sb.toString();
    }

    private static String axios(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("const axios = require(\"axios\");\n\n");
        sb.append("const response = await axios({\n");
        sb.append("  method: \"").append(d.method).append("\".toLowerCase(),\n");
        sb.append("  url: \"").append(escJs(d.url)).append("\",\n");

        if (!d.headers.isEmpty()) {
            sb.append("  headers: {\n");
            for (Map.Entry<String, String> e : d.headers.entrySet()) {
                sb.append("    \"").append(escJs(e.getKey())).append("\": \"").append(escJs(e.getValue())).append("\",\n");
            }
            sb.append("  },\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("  headers: { ...this?.headers, \"Cookie\": \"").append(escJs(joinCookies(d.cookies))).append("\" },\n");
        }

        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("  data: ").append(d.body).append(",\n");
            } else {
                sb.append("  data: ").append(escJsTemplateLiteral(d.body)).append(",\n");
            }
        }

        sb.append("});\n\nconsole.log(response.status);\nconsole.log(response.data);\n");
        return sb.toString();
    }

    private static String php(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("<?php\n\n");
        sb.append("$ch = curl_init();\n");
        sb.append("curl_setopt($ch, CURLOPT_URL, \"").append(escDq(d.url)).append("\");\n");
        sb.append("curl_setopt($ch, CURLOPT_CUSTOMREQUEST, \"").append(d.method).append("\");\n");
        sb.append("curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n");

        if (!d.headers.isEmpty()) {
            sb.append("$headers = [\n");
            for (Map.Entry<String, String> e : d.headers.entrySet()) {
                sb.append("    \"").append(e.getKey()).append(": ").append(escDq(e.getValue())).append("\",\n");
            }
            sb.append("];\ncurl_setopt($ch, CURLOPT_HTTPHEADER, $headers);\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("curl_setopt($ch, CURLOPT_COOKIE, \"").append(escDq(joinCookies(d.cookies))).append("\");\n");
        }

        if (!d.body.isEmpty()) {
            sb.append("curl_setopt($ch, CURLOPT_POSTFIELDS, ").append(escPhpSingleQuote(d.body)).append(");\n");
        }

        sb.append("$response = curl_exec($ch);\n");
        sb.append("$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);\n");
        sb.append("curl_close($ch);\n\necho $statusCode . \"\\n\";\necho $response . \"\\n\";\n?>\n");
        return sb.toString();
    }

    private static String ruby(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("require \"net/http\"\nrequire \"uri\"\nrequire \"json\"\n\n");
        sb.append("uri = URI.parse(\"").append(escDq(d.url)).append("\")\n\n");

        String methodClass = d.method.substring(0, 1).toUpperCase() + d.method.substring(1).toLowerCase();
        String[] valid = {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options"};
        boolean found = false;
        for (String m : valid) {
            if (m.equals(methodClass)) { found = true; break; }
        }
        if (found) {
            sb.append("request = Net::HTTP::").append(methodClass).append(".new(uri)\n");
        } else {
            sb.append("request = Net::HTTPGenericRequest.new(\"").append(d.method).append("\", true, nil, uri)\n");
        }

        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append("request[\"").append(escRb(e.getKey())).append("\"] = \"").append(escRb(e.getValue())).append("\"\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("request[\"Cookie\"] = \"").append(escRb(joinCookies(d.cookies))).append("\"\n");
        }

        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("request.body = ").append(d.body).append(".to_json\n");
            } else {
                sb.append("request.body = ").append(escDoubleQuote(d.body)).append("\n");
            }
        }

        sb.append("\nresponse = Net::HTTP.start(uri.hostname, uri.port, :use_ssl => uri.scheme == \"https\") do |http|\n");
        sb.append("  http.request(request)\nend\n\nputs response.code\nputs response.body\n");
        return sb.toString();
    }

    private static String csharp(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("using System;\n");
        sb.append("using System.Net.Http;\n");
        sb.append("using System.Text;\n");
        sb.append("using System.Threading.Tasks;\n\n");
        sb.append("class Program\n{\n");
        sb.append("    static async Task Main()\n    {\n");
        sb.append("        using var client = new HttpClient();\n");

        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            if (e.getKey().equalsIgnoreCase("Accept")) {
                sb.append("        client.DefaultRequestHeaders.Add(\"Accept\", \"").append(escCs(e.getValue())).append("\");\n");
            } else {
                sb.append("        client.DefaultRequestHeaders.Add(\"").append(escCs(e.getKey()))
                        .append("\", \"").append(escCs(e.getValue())).append("\");\n");
            }
        }

        if (!d.cookies.isEmpty()) {
            sb.append("        client.DefaultRequestHeaders.Add(\"Cookie\", \"").append(escCs(joinCookies(d.cookies))).append("\");\n");
        }

        String bodyVar = "null";
        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("        var json = @\"").append(escCs(d.body)).append("\";\n");
                sb.append("        var content = new StringContent(json, Encoding.UTF8, \"application/json\");\n");
            } else {
                sb.append("        var body = @\"").append(escCs(d.body)).append("\";\n");
                sb.append("        var content = new StringContent(body, Encoding.UTF8, \"").append(escCs(d.contentType)).append("\");\n");
            }
            bodyVar = "content";
        }

        sb.append("\n        var response = await client.").append(d.method.substring(0, 1).toUpperCase() + d.method.substring(1).toLowerCase())
                .append("Async(\"").append(escCs(d.url)).append("\", ").append(bodyVar).append(");\n");
        sb.append("        var responseBody = await response.Content.ReadAsStringAsync();\n\n");
        sb.append("        Console.WriteLine(response.StatusCode);\n");
        sb.append("        Console.WriteLine(responseBody);\n");
        sb.append("    }\n}\n");
        return sb.toString();
    }

    private static String java(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("import java.net.URI;\n");
        sb.append("import java.net.http.HttpClient;\n");
        sb.append("import java.net.http.HttpRequest;\n");
        sb.append("import java.net.http.HttpResponse;\n\n");
        sb.append("public class Main {\n");
        sb.append("    public static void main(String[] args) throws Exception {\n");
        sb.append("        HttpClient client = HttpClient.newHttpClient();\n\n");

        String bodyBuilder;
        if (!d.body.isEmpty()) {
            bodyBuilder = "                .POST(HttpRequest.BodyPublishers.ofString(\"\"\"\n                    " + d.body + "\n                \"\"\"))";
        } else if ("GET".equals(d.method)) {
            bodyBuilder = "                .GET()";
        } else {
            bodyBuilder = "                .method(\"" + d.method + "\", HttpRequest.BodyPublishers.noBody())";
        }

        sb.append("        HttpRequest request = HttpRequest.newBuilder()\n");
        sb.append("                .uri(URI.create(\"").append(escJava(d.url)).append("\"))\n");
        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append("                .header(\"").append(escJava(e.getKey())).append("\", \"").append(escJava(e.getValue())).append("\")\n");
        }
        if (!d.cookies.isEmpty()) {
            sb.append("                .header(\"Cookie\", \"").append(escJava(joinCookies(d.cookies))).append("\")\n");
        }
        sb.append(bodyBuilder).append("\n");
        sb.append("                .build();\n\n");
        sb.append("        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());\n\n");
        sb.append("        System.out.println(response.statusCode());\n");
        sb.append("        System.out.println(response.body());\n");
        sb.append("    }\n}\n");
        return sb.toString();
    }

    private static String powershell(RequestData d) {
        StringBuilder sb = new StringBuilder();
        if (!d.headers.isEmpty()) {
            sb.append("$headers = @{\n");
            for (Map.Entry<String, String> e : d.headers.entrySet()) {
                sb.append("    \"").append(escPs(e.getKey())).append("\" = \"").append(escPs(e.getValue())).append("\"\n");
            }
            sb.append("}\n\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession\n");
            sb.append("$cookie = New-Object System.Net.Cookie\n");
            for (Map.Entry<String, String> e : d.cookies.entrySet()) {
                sb.append("$cookie = New-Object System.Net.Cookie(\"").append(escPs(e.getKey()))
                        .append("\", \"").append(escPs(e.getValue())).append("\", \"/\", $null)\n");
                sb.append("$session.Cookies.Add($cookie)\n");
            }
            sb.append("\n");
        }

        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("$body = @'\n").append(d.body).append("\n'@\n\n");
            } else {
                sb.append("$body = \"").append(escPs(d.body)).append("\"\n\n");
            }
        }

        List<String> callLines = new ArrayList<>();
        callLines.add("$response = Invoke-RestMethod \\");
        callLines.add("    -Method " + d.method + " \\");
        callLines.add("    -Uri \"" + d.url + "\" \\");
        if (!d.headers.isEmpty()) callLines.add("    -Headers $headers \\");
        if (!d.body.isEmpty()) callLines.add("    -Body $body \\");
        if (!d.cookies.isEmpty()) callLines.add("    -WebSession $session \\");

        for (int i = 0; i < callLines.size() - 1; i++) {
            sb.append(callLines.get(i)).append("\n");
        }
        sb.append(callLines.get(callLines.size() - 1)).append("\n\n");
        sb.append("Write-Output $response.StatusCode\n");
        sb.append("Write-Output $response.Content\n");
        return sb.toString();
    }

    private static String rust(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("use std::collections::HashMap;\n\n");
        sb.append("#[tokio::main]\nasync fn main() -> Result<(), Box<dyn std::error::Error>> {\n");
        sb.append("    let client = reqwest::Client::new();\n\n");

        String methodLower = d.method.toLowerCase();
        String[] valid = {"get", "post", "put", "patch", "delete", "head"};
        boolean found = false;
        for (String m : valid) {
            if (m.equals(methodLower)) { found = true; break; }
        }
        String call = found ? "client." + methodLower : "client.request(reqwest::Method::from_bytes(b\"" + d.method + "\")?)";

        sb.append("    let mut request = ").append(call).append("(\"").append(d.url).append("\");\n");

        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append("    request = request.header(\"").append(escRs(e.getKey())).append("\", \"")
                    .append(escRs(e.getValue())).append("\");\n");
        }

        if (!d.cookies.isEmpty()) {
            sb.append("    request = request.header(\"Cookie\", \"").append(escRs(joinCookies(d.cookies))).append("\");\n");
        }

        if (!d.body.isEmpty()) {
            if (d.hasJsonBody()) {
                sb.append("    request = request.json(&serde_json::json!(").append(d.body).append("));\n");
            } else {
                sb.append("    request = request.body(\"").append(escRs(d.body)).append("\");\n");
            }
        }

        sb.append("\n    let response = request.send().await?;\n");
        sb.append("    let status = response.status();\n");
        sb.append("    let body = response.text().await?;\n\n");
        sb.append("    println!(\"{}\", status);\n");
        sb.append("    println!(\"{}\", body);\n\n");
        sb.append("    Ok(())\n}\n");
        return sb.toString();
    }

    private static String wget(RequestData d) {
        StringBuilder sb = new StringBuilder();
        sb.append("wget -q -O -");
        if (!"GET".equals(d.method)) {
            sb.append(" \\\n  --method=").append(d.method);
        }
        for (Map.Entry<String, String> e : d.headers.entrySet()) {
            sb.append(" \\\n  --header=\"").append(e.getKey()).append(": ").append(escDq(e.getValue())).append("\"");
        }
        if (!d.cookies.isEmpty()) {
            sb.append(" \\\n  --header=\"Cookie: ").append(joinCookies(d.cookies)).append("\"");
        }
        if (!d.body.isEmpty()) {
            sb.append(" \\\n  --body-data=").append(escShellSingleQuote(d.body));
        }
        sb.append(" \\\n  \"").append(d.url).append("\"");
        return sb.toString();
    }

    // --- Helpers -------------------------------------------------------------

    private static String joinCookies(Map<String, String> cookies) {
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (Map.Entry<String, String> e : cookies.entrySet()) {
            if (!first) sb.append("; ");
            sb.append(e.getKey()).append("=").append(e.getValue());
            first = false;
        }
        return sb.toString();
    }

    private static String escPy(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private static String escDq(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String escGoRawString(String s) {
        if (s.indexOf('`') < 0) return "`" + s + "`";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    private static String escJs(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private static String escJsTemplateLiteral(String s) {
        return "`" + s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${") + "`";
    }

    private static String escShellSingleQuote(String s) {
        return "'" + s.replace("'", "'\\''") + "'";
    }

    private static String escPhpSingleQuote(String s) {
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'";
    }

    private static String escRb(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t").replace("#", "\\#");
    }

    private static String escDoubleQuote(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private static String escCs(String s) {
        return s.replace("\"", "\"\"");
    }

    private static String escJava(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private static String escPs(String s) {
        return s.replace("'", "''");
    }

    private static String escRs(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    // --- Mini JSON parser / Python emitter -----------------------------------

    private static class MiniJson {
        private final String src;
        private int pos;

        private MiniJson(String s) { this.src = s; this.pos = 0; }

        static Object parse(String s) {
            MiniJson p = new MiniJson(s);
            p.skipWs();
            Object v = p.readValue();
            p.skipWs();
            if (p.pos != p.src.length()) {
                throw new RuntimeException("trailing");
            }
            return v;
        }

        private void skipWs() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private Object readValue() {
            skipWs();
            if (pos >= src.length()) throw new RuntimeException("eof");
            char c = src.charAt(pos);
            if (c == '{') return readObject();
            if (c == '[') return readArray();
            if (c == '"') return readString();
            if (c == 't' || c == 'f') return readBool();
            if (c == 'n') return readNull();
            return readNumber();
        }

        private java.util.Map<String, Object> readObject() {
            java.util.LinkedHashMap<String, Object> m = new java.util.LinkedHashMap<>();
            pos++; skipWs();
            if (pos < src.length() && src.charAt(pos) == '}') { pos++; return m; }
            while (true) {
                skipWs();
                String k = readString();
                skipWs();
                if (pos >= src.length() || src.charAt(pos) != ':') throw new RuntimeException("expected :");
                pos++;
                Object v = readValue();
                m.put(k, v);
                skipWs();
                if (pos < src.length() && src.charAt(pos) == ',') { pos++; continue; }
                if (pos < src.length() && src.charAt(pos) == '}') { pos++; return m; }
                throw new RuntimeException("expected , or }");
            }
        }

        private java.util.List<Object> readArray() {
            java.util.ArrayList<Object> a = new java.util.ArrayList<>();
            pos++; skipWs();
            if (pos < src.length() && src.charAt(pos) == ']') { pos++; return a; }
            while (true) {
                a.add(readValue());
                skipWs();
                if (pos < src.length() && src.charAt(pos) == ',') { pos++; continue; }
                if (pos < src.length() && src.charAt(pos) == ']') { pos++; return a; }
                throw new RuntimeException("expected , or ]");
            }
        }

        private String readString() {
            if (src.charAt(pos) != '"') throw new RuntimeException("expected \"");
            pos++;
            StringBuilder sb = new StringBuilder();
            while (pos < src.length()) {
                char c = src.charAt(pos);
                if (c == '"') { pos++; return sb.toString(); }
                if (c == '\\' && pos + 1 < src.length()) {
                    char n = src.charAt(pos + 1);
                    switch (n) {
                        case '"': sb.append('"'); break;
                        case '\\': sb.append('\\'); break;
                        case '/': sb.append('/'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'u':
                            if (pos + 5 < src.length()) {
                                sb.append((char) Integer.parseInt(src.substring(pos + 2, pos + 6), 16));
                                pos += 4;
                            }
                            break;
                        default: sb.append(n);
                    }
                    pos += 2;
                } else {
                    sb.append(c);
                    pos++;
                }
            }
            throw new RuntimeException("unterminated string");
        }

        private Object readNumber() {
            int start = pos;
            if (src.charAt(pos) == '-') pos++;
            while (pos < src.length() && "0123456789.eE+-".indexOf(src.charAt(pos)) >= 0) pos++;
            String n = src.substring(start, pos);
            if (n.contains(".") || n.contains("e") || n.contains("E")) {
                return Double.parseDouble(n);
            }
            try {
                return Long.parseLong(n);
            } catch (NumberFormatException e) {
                return Double.parseDouble(n);
            }
        }

        private Object readBool() {
            if (src.startsWith("true", pos)) { pos += 4; return Boolean.TRUE; }
            if (src.startsWith("false", pos)) { pos += 5; return Boolean.FALSE; }
            throw new RuntimeException("bad bool");
        }

        private Object readNull() {
            if (src.startsWith("null", pos)) { pos += 4; return null; }
            throw new RuntimeException("bad null");
        }

        static String toPythonLiteral(Object v, int depth) {
            if (v == null) return "None";
            if (v instanceof Boolean) return ((Boolean) v) ? "True" : "False";
            if (v instanceof Number) return v.toString();
            if (v instanceof String) return "\"" + escPy((String) v) + "\"";
            if (v instanceof java.util.List) {
                StringBuilder sb = new StringBuilder("[");
                boolean first = true;
                for (Object item : (java.util.List<?>) v) {
                    if (!first) sb.append(", ");
                    sb.append(toPythonLiteral(item, depth + 1));
                    first = false;
                }
                return sb.append("]").toString();
            }
            if (v instanceof java.util.Map) {
                StringBuilder sb = new StringBuilder("{\n");
                String pad = repeat("    ", depth + 1);
                boolean first = true;
                for (Map.Entry<?, ?> e : ((java.util.Map<?, ?>) v).entrySet()) {
                    if (!first) sb.append(",\n");
                    sb.append(pad).append("\"").append(escPy(e.getKey().toString())).append("\": ")
                            .append(toPythonLiteral(e.getValue(), depth + 1));
                    first = false;
                }
                sb.append("\n").append(repeat("    ", depth)).append("}");
                return sb.toString();
            }
            return "\"" + escPy(v.toString()) + "\"";
        }

        private static String repeat(String s, int n) {
            StringBuilder sb = new StringBuilder(s.length() * n);
            for (int i = 0; i < n; i++) sb.append(s);
            return sb.toString();
        }
    }
}
