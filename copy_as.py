from burp import IBurpExtender, IContextMenuFactory
from javax.swing import JMenuItem
from java.util import ArrayList
import json


class BurpExtender(IBurpExtender):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        callbacks.setExtensionName("CopyAs")
        callbacks.registerContextMenuFactory(MenuFactory(callbacks))
        print("[*] CopyAs loaded")


class MenuFactory(IContextMenuFactory):
    def __init__(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()

    def createMenuItems(self, inv):
        items = ArrayList()
        menu_entries = [
            ("Copy As: Python (requests)", self._python),
            ("Copy As: Go (net/http)", self._go),
            ("Copy As: cURL", self._curl),
            ("Copy As: JavaScript (fetch)", self._fetch),
            ("Copy As: JavaScript (axios)", self._axios),
            ("Copy As: PHP (curl)", self._php),
            ("Copy As: Ruby (net/http)", self._ruby),
            ("Copy As: C# (HttpClient)", self._csharp),
            ("Copy As: Java (HttpClient)", self._java),
            ("Copy As: PowerShell", self._powershell),
            ("Copy As: Rust (reqwest)", self._rust),
            ("Copy As: wget", self._wget),
        ]
        for label, fn in menu_entries:
            mi = JMenuItem(label)
            mi.addActionListener(lambda e, f=fn, i=inv: f(i))
            items.add(mi)
        return items

    def _python(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = ["import requests", "", 'url = "%s"' % data["url"]]

        if data["headers"]:
            lines += ["", "headers = {"]
            for k, v in sorted(data["headers"].items()):
                lines.append('    "%s": "%s",' % (_esc_py(k), _esc_py(v)))
            lines += ["}"]

        if data["cookies"]:
            lines += ["", "cookies = {"]
            for k, v in sorted(data["cookies"].items()):
                lines.append('    "%s": "%s",' % (_esc_py(k), _esc_py(v)))
            lines += ["}"]

        body_arg = ""
        if data["body"]:
            if "json" in data["content_type"]:
                try:
                    json_obj = json.loads(data["body"])
                    json_str = json.dumps(json_obj, indent=4)
                    json_str = json_str.replace(': null', ': None').replace(': true', ': True').replace(': false', ': False')
                    lines += ["", "json_body = %s" % json_str]
                    body_arg = ", json=json_body"
                except (ValueError, TypeError):
                    lines += ["", 'data = \'\'\'%s\'\'\'' % data["body"]]
                    body_arg = ", data=data"
            else:
                lines += ["", 'data = \'\'\'%s\'\'\'' % data["body"]]
                body_arg = ", data=data"

        method = data["method"].lower()
        valid_methods = ["get", "post", "put", "patch", "delete", "head", "options"]
        if method in valid_methods:
            call = "requests.%s(url" % method
        else:
            call = "requests.request('%s', url" % data["method"]

        kwargs = []
        if data["headers"]:
            kwargs.append("headers=headers")
        if data["cookies"]:
            kwargs.append("cookies=cookies")
        if body_arg:
            kwargs.append(body_arg.lstrip(", "))

        lines.append("")
        if kwargs:
            lines.append("response = %s, %s)" % (call, ", ".join(kwargs)))
        else:
            lines.append("response = %s)" % call)
        lines += ["", "print(response.status_code)", "print(response.text)"]
        self._copy("\n".join(lines))

    def _go(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'package main', '',
            'import (',
            '\t"fmt"',
            '\t"io"',
            '\t"net/http"',
            '\t"strings"',
            ')', '',
            'func main() {',
        ]

        if data["body"]:
            lines.append('\tbody := strings.NewReader(%s)' % _esc_go_raw_string(data["body"]))
        lines.append('\treq, _ := http.NewRequest("%s", "%s", %s)' % (
            data["method"], data["url"], "body" if data["body"] else "nil"))

        for k, v in sorted(data["headers"].items()):
            lines.append('\treq.Header.Set("%s", "%s")' % (_esc_dq(k), _esc_dq(v)))
        for k, v in sorted(data["cookies"].items()):
            lines.append('\treq.AddCookie(&http.Cookie{Name: "%s", Value: "%s"})' % (_esc_dq(k), _esc_dq(v)))

        lines += [
            '',
            '\tresp, _ := http.DefaultClient.Do(req)',
            '\tdefer resp.Body.Close()',
            '',
            '\tdata, _ := io.ReadAll(resp.Body)',
            '\tfmt.Println(resp.StatusCode)',
            '\tfmt.Println(string(data))',
            '}',
        ]
        self._copy("\n".join(lines))

    def _curl(self, inv):
        data = self._parse(inv)
        if not data:
            return
        parts = ['curl -s -X %s "%s"' % (data["method"], data["url"])]
        for k, v in sorted(data["headers"].items()):
            parts.append('  -H "%s: %s"' % (k, _esc_dq(v)))
        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            parts.append('  -H "Cookie: %s"' % cookie_str)
        if data["body"]:
            parts.append("  --data-raw %s" % _esc_shell_single_quote(data["body"]))
        self._copy(" \\\n".join(parts))

    def _fetch(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'const response = await fetch("%s", {' % data["url"],
            '  method: "%s",' % data["method"],
        ]

        if data["headers"]:
            lines += ["  headers: {"]
            for k, v in sorted(data["headers"].items()):
                lines.append('    "%s": "%s",' % (_esc_js(k), _esc_js(v)))
            lines += ["},"]

        if data["body"]:
            if "json" in data["content_type"]:
                lines.append("  body: JSON.stringify(%s)," % data["body"])
            else:
                lines.append("  body: %s," % _esc_js_template_literal(data["body"]))

        lines += ["});", "", "console.log(response.status);", "console.log(await response.text());"]
        self._copy("\n".join(lines))

    def _php(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            '<?php', '',
            '$ch = curl_init();',
            'curl_setopt($ch, CURLOPT_URL, "%s");' % data["url"],
            'curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "%s");' % data["method"],
            'curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);',
        ]

        if data["headers"]:
            lines.append("$headers = [")
            for k, v in sorted(data["headers"].items()):
                lines.append('    "%s: %s",' % (k, _esc_dq(v)))
            lines += ["];", "curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);"]

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('curl_setopt($ch, CURLOPT_COOKIE, "%s");' % _esc_dq(cookie_str))

        if data["body"]:
            lines.append("curl_setopt($ch, CURLOPT_POSTFIELDS, %s);" % _esc_php_single_quote(data["body"]))

        lines += [
            '$response = curl_exec($ch);',
            '$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);',
            'curl_close($ch);', '',
            'echo $statusCode . "\\n";',
            'echo $response . "\\n";',
            '?>',
        ]
        self._copy("\n".join(lines))

    def _axios(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'const axios = require("axios");',
            '',
            'const response = await axios({',
            '  method: "%s".toLowerCase(),' % data["method"],
            '  url: "%s",' % data["url"],
        ]

        if data["headers"]:
            lines += ["  headers: {"]
            for k, v in sorted(data["headers"].items()):
                lines.append('    "%s": "%s",' % (_esc_js(k), _esc_js(v)))
            lines += ["  },"]

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('  headers: { ...this?.headers, "Cookie": "%s" },' % _esc_js(cookie_str))

        if data["body"]:
            if "json" in data["content_type"]:
                lines.append("  data: %s," % data["body"])
            else:
                lines.append("  data: %s," % _esc_js_template_literal(data["body"]))

        lines += [
            "});",
            "",
            "console.log(response.status);",
            "console.log(response.data);",
        ]
        self._copy("\n".join(lines))

    def _ruby(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'require "net/http"',
            'require "uri"',
            'require "json"',
            '',
            'uri = URI.parse("%s")' % data["url"],
            '',
        ]

        method_class = data["method"].capitalize()
        if method_class in ["Get", "Post", "Put", "Patch", "Delete", "Head", "Options"]:
            lines.append('request = Net::HTTP::%s.new(uri)' % method_class)
        else:
            lines.append('request = Net::HTTPGenericRequest.new("%s", true, nil, uri)' % data["method"])

        for k, v in sorted(data["headers"].items()):
            lines.append('request["%s"] = "%s"' % (_esc_rb(k), _esc_rb(v)))

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('request["Cookie"] = "%s"' % _esc_rb(cookie_str))

        if data["body"]:
            if "json" in data["content_type"]:
                lines.append("request.body = %s.to_json" % data["body"])
            else:
                lines.append('request.body = %s' % _esc_double_quote(data["body"]))

        lines += [
            '',
            'response = Net::HTTP.start(uri.hostname, uri.port, :use_ssl => uri.scheme == "https") do |http|',
            '  http.request(request)',
            'end',
            '',
            'puts response.code',
            'puts response.body',
        ]
        self._copy("\n".join(lines))

    def _csharp(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'using System;',
            'using System.Net.Http;',
            'using System.Text;',
            'using System.Threading.Tasks;',
            '',
            'class Program',
            '{',
            '    static async Task Main()',
            '    {',
            '        using var client = new HttpClient();',
        ]

        if data["headers"]:
            for k, v in sorted(data["headers"].items()):
                if k.lower() == "accept":
                    lines.append('        client.DefaultRequestHeaders.Add("Accept", "%s");' % _esc_cs(v))
                else:
                    lines.append('        client.DefaultRequestHeaders.Add("%s", "%s");' % (_esc_cs(k), _esc_cs(v)))

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('        client.DefaultRequestHeaders.Add("Cookie", "%s");' % _esc_cs(cookie_str))

        body_var = "null"
        content_type_var = ""
        if data["body"]:
            if "json" in data["content_type"]:
                lines.append('        var json = @"%s";' % _esc_cs(data["body"]))
                lines.append('        var content = new StringContent(json, Encoding.UTF8, "application/json");')
                body_var = "content"
            else:
                lines.append('        var body = @"%s";' % _esc_cs(data["body"]))
                lines.append('        var content = new StringContent(body, Encoding.UTF8, "%s");' % _esc_cs(data["content_type"]))
                body_var = "content"

        lines.append('')
        lines.append('        var response = await client.%sAsync("%s", %s);' % (data["method"].capitalize(), data["url"], body_var))
        lines.append('        var responseBody = await response.Content.ReadAsStringAsync();')
        lines.append('')
        lines.append('        Console.WriteLine(response.StatusCode);')
        lines.append('        Console.WriteLine(responseBody);')
        lines += ['   ', '}']
        self._copy("\n".join(lines))

    def _java(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'import java.net.URI;',
            'import java.net.http.HttpClient;',
            'import java.net.http.HttpRequest;',
            'import java.net.http.HttpResponse;',
            '',
            'public class Main {',
            '    public static void main(String[] args) throws Exception {',
            '        HttpClient client = HttpClient.newHttpClient();',
            '',
        ]

        body_builder = ""
        if data["body"]:
            if "json" in data["content_type"]:
                body_builder = '                .POST(HttpRequest.BodyPublishers.ofString("""\n                    %s\n                """))' % data["body"]
            else:
                body_builder = '                .POST(HttpRequest.BodyPublishers.ofString("""\n                    %s\n                """))' % data["body"]
        else:
            if data["method"] == "GET":
                body_builder = '                .GET()'
            else:
                body_builder = '                .method("%s", HttpRequest.BodyPublishers.noBody())' % data["method"]

        header_lines = []
        for k, v in sorted(data["headers"].items()):
            header_lines.append('                .header("%s", "%s")' % (_esc_java(k), _esc_java(v)))
        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            header_lines.append('                .header("Cookie", "%s")' % _esc_java(cookie_str))

        lines += [
            '        HttpRequest request = HttpRequest.newBuilder()',
            '                .uri(URI.create("%s"))' % data["url"],
        ]
        lines += header_lines
        lines.append(body_builder)
        lines += [
            '                .build();',
            '',
            '        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());',
            '',
            '        System.out.println(response.statusCode());',
            '        System.out.println(response.body());',
            '    }',
            '}',
        ]
        self._copy("\n".join(lines))

    def _powershell(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = []

        if data["headers"]:
            lines.append("$headers = @{")
            for k, v in sorted(data["headers"].items()):
                lines.append('    "%s" = "%s"' % (_esc_ps(k), _esc_ps(v)))
            lines += ["}", ""]

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession')
            lines.append('$cookie = New-Object System.Net.Cookie')
            for k, v in sorted(data["cookies"].items()):
                lines.append('$cookie = New-Object System.Net.Cookie("%s", "%s", "/", $null)' % (_esc_ps(k), _esc_ps(v)))
                lines.append('$session.Cookies.Add($cookie)')
            lines.append("")

        if data["body"]:
            if "json" in data["content_type"]:
                lines.append("$body = @'")
                lines.append(data["body"])
                lines += ["'@", ""]
            else:
                lines.append('$body = "%s"' % _esc_ps(data["body"]))
                lines.append("")

        call = "Invoke-RestMethod"
        lines.append('$response = %s \\' % call)
        lines.append('    -Method %s \\' % data["method"])
        lines.append('    -Uri "%s" \\' % data["url"])
        if data["headers"]:
            lines.append('    -Headers $headers \\')
        if data["body"]:
            lines.append('    -Body $body \\')
        if data["cookies"]:
            lines.append('    -WebSession $session \\')
        lines = lines[:-1]  # remove trailing backslash

        lines += [
            "",
            'Write-Output $response.StatusCode',
            'Write-Output $response.Content',
        ]
        self._copy("\n".join(lines))

    def _rust(self, inv):
        data = self._parse(inv)
        if not data:
            return
        lines = [
            'use std::collections::HashMap;',
            '',
            '#[tokio::main]',
            'async fn main() -> Result<(), Box<dyn std::error::Error>> {',
            '    let client = reqwest::Client::new();',
            '',
        ]

        method_lower = data["method"].lower()
        valid_methods = ["get", "post", "put", "patch", "delete", "head"]
        if method_lower in valid_methods:
            call = "client.%s" % method_lower
        else:
            call = 'client.request(reqwest::Method::from_bytes(b"%s")?)' % data["method"]

        lines.append('    let mut request = %s("%s");' % (call, data["url"]))

        if data["headers"]:
            for k, v in sorted(data["headers"].items()):
                lines.append('    request = request.header("%s", "%s");' % (_esc_rs(k), _esc_rs(v)))

        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            lines.append('    request = request.header("Cookie", "%s");' % _esc_rs(cookie_str))

        if data["body"]:
            if "json" in data["content_type"]:
                lines.append("    request = request.json(&serde_json::json!(%s));" % data["body"])
            else:
                lines.append('    request = request.body(%s);' % _esc_rs(data["body"]))

        lines += [
            "",
            "    let response = request.send().await?;",
            "    let status = response.status();",
            "    let body = response.text().await?;",
            "",
            '    println!("{}", status);',
            '    println!("{}", body);',
            "",
            "    Ok(())",
            "}",
        ]
        self._copy("\n".join(lines))

    def _wget(self, inv):
        data = self._parse(inv)
        if not data:
            return
        parts = ['wget -q -O -']
        if data["method"] != "GET":
            parts.append('--method=%s' % data["method"])
        for k, v in sorted(data["headers"].items()):
            parts.append('  --header="%s: %s"' % (k, _esc_dq(v)))
        if data["cookies"]:
            cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(data["cookies"].items()))
            parts.append('  --header="Cookie: %s"' % cookie_str)
        if data["body"]:
            parts.append('  --body-data=%s' % _esc_shell_single_quote(data["body"]))
        parts.append('  "%s"' % data["url"])
        self._copy(" \\\n".join(parts))

    def _parse(self, inv):
        messages = None
        try:
            messages = inv.getSelectedMessages()
        except AttributeError:
            try:
                messages = inv.selectedMessages
            except AttributeError:
                return None

        if messages is None or len(messages) == 0:
            return None

        msg = messages[0]

        svc = None
        req = None
        try:
            svc = msg.getHttpService()
            req = msg.getRequest()
        except AttributeError:
            try:
                svc = msg.httpService
                req = msg.request
            except AttributeError:
                return None

        analyzed = self._helpers.analyzeRequest(svc, req)
        headers = list(analyzed.getHeaders())
        body_offset = analyzed.getBodyOffset()

        try:
            req_bytes = req.tostring() if hasattr(req, 'tostring') else str(req)
            body = req_bytes[body_offset:] if body_offset < len(req_bytes) else ""
        except Exception:
            body = ""

        method = headers[0].split(" ")[0] if headers else "GET"
        path = headers[0].split(" ")[1] if headers else "/"

        host = ""
        port = 443
        protocol = "https"
        try:
            host = svc.getHost()
            port = svc.getPort()
            protocol = svc.getProtocol()
        except AttributeError:
            try:
                host = svc.host
                port = svc.port
                protocol = svc.protocol
            except AttributeError:
                pass

        if protocol == "https" and port == 443:
            url = "https://%s%s" % (host, path)
        elif protocol == "http" and port == 80:
            url = "http://%s%s" % (host, path)
        else:
            url = "%s://%s:%s%s" % (protocol, host, port, path)

        parsed_headers = {}
        parsed_cookies = {}
        content_type = ""
        for hdr in headers[1:]:
            if hdr.lower().startswith("cookie:"):
                for part in hdr[7:].split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parsed_cookies[k.strip()] = v.strip()
            elif ":" in hdr:
                k, v = hdr.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k.lower() == "content-type":
                    content_type = v
                if k.lower() not in ["host", "connection", "content-length"]:
                    parsed_headers[k] = v

        return {
            "method": method,
            "url": url,
            "headers": parsed_headers,
            "cookies": parsed_cookies,
            "body": body,
            "content_type": content_type,
        }

    def _copy(self, text):
        from java.awt import Toolkit
        from java.awt.datatransfer import StringSelection
        cb = Toolkit.getDefaultToolkit().getSystemClipboard()
        cb.setContents(StringSelection(text), None)
        print("[*] Copied to clipboard")


def _esc_py(s):
    """Escape a string for use inside a Python double-quoted string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def _esc_dq(s):
    """Escape a string for use inside a double-quoted string literal (Go, PHP, etc.)."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    return s


def _esc_triple_quote(s):
    """Escape a string for use inside a Python triple-quoted string."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"""', '\\"\\"\\"')
    return s


def _esc_go_raw_string(s):
    """Escape a string for use inside a Go raw string literal (backtick-delimited)."""
    if '`' not in s:
        return '`%s`' % s
    # Go raw strings cannot contain backticks; fall back to interpreted string
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return '"%s"' % s


def _esc_js(s):
    """Escape a string for use inside a JavaScript double-quoted string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def _esc_js_template_literal(s):
    """Escape a string for use inside a JavaScript template literal (backtick-delimited)."""
    s = s.replace('\\', '\\\\')
    s = s.replace('`', '\\`')
    s = s.replace('${', '\\${')
    return '`%s`' % s


def _esc_shell_single_quote(s):
    """Escape a string for use as a shell single-quoted argument."""
    # In POSIX shells, single quotes cannot contain single quotes.
    # The idiomatic workaround is: end quote, escaped single quote, start quote.
    return "'%s'" % s.replace("'", "'\\''")


def _esc_php_single_quote(s):
    """Escape a string for use inside a PHP single-quoted string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace("'", "\\'")
    return "'%s'" % s


def _esc_rb(s):
    """Escape a string for use inside a Ruby double-quoted string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    s = s.replace('#', '\\#')
    return s


def _esc_double_quote(s):
    """Escape a string for use inside a generic double-quoted string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def _esc_cs(s):
    """Escape a string for use inside a C# verbatim string literal (@""...")."""
    s = s.replace('"', '""')
    return s


def _esc_java(s):
    """Escape a string for use inside a Java string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def _esc_ps(s):
    """Escape a string for use inside a PowerShell single-quoted string literal."""
    s = s.replace("'", "''")
    return s


def _esc_rs(s):
    """Escape a string for use inside a Rust string literal."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s
