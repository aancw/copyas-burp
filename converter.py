#!/usr/bin/env python3
"""
HTTP Request Converter
Converts raw HTTP request text to code in multiple languages.

Usage:
    python converter.py < request.txt
    python converter.py --file request.txt
    python converter.py --url https://example.com
    python converter.py --file request.txt --format go
    python converter.py --file request.txt --format all
"""

import sys
import json
import argparse
import re


SUPPORTED_FORMATS = [
    "python", "go", "curl", "fetch", "axios", "php",
    "ruby", "csharp", "java", "powershell", "rust", "wget",
]


def parse_raw_http_request(raw_request):
    """Parse a raw HTTP request into its components."""
    raw_request = raw_request.replace('\r\n', '\n').replace('\r', '\n')

    if '\n\n' in raw_request:
        header_section, body = raw_request.split('\n\n', 1)
    else:
        header_section = raw_request
        body = ""

    lines = header_section.split('\n')

    request_line = lines[0].strip()
    parts = request_line.split(' ')
    if len(parts) < 2:
        raise ValueError("Invalid HTTP request line: %s" % request_line)

    method = parts[0].upper()
    path = parts[1]
    http_version = parts[2] if len(parts) > 2 else 'HTTP/1.1'

    headers = {}
    cookies = {}
    host = ""
    port = 443
    protocol = "https"

    for line in lines[1:]:
        line = line.strip()
        if not line or ':' not in line:
            continue

        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()

        if key.lower() == 'host':
            host = value
            if ':' in host:
                host, port_str = host.rsplit(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    pass
            protocol = "https" if port == 443 else "http"
        elif key.lower() == 'cookie':
            for part in value.split(';'):
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    cookies[k.strip()] = v.strip()
        else:
            headers[key] = value

    return {
        'method': method,
        'path': path,
        'protocol': protocol,
        'host': host,
        'port': port,
        'headers': headers,
        'cookies': cookies,
        'body': body.strip(),
    }


def build_url(parsed):
    """Build full URL from parsed components."""
    protocol = parsed['protocol']
    host = parsed['host']
    port = parsed['port']
    path = parsed['path']

    if protocol == 'https' and port == 443:
        return "https://%s%s" % (host, path)
    elif protocol == 'http' and port == 80:
        return "http://%s%s" % (host, path)
    else:
        return "%s://%s:%s%s" % (protocol, host, port, path)


def get_content_type(headers):
    """Get Content-Type header value, case-insensitive."""
    for k, v in headers.items():
        if k.lower() == 'content-type':
            return v
    return ''


# --- Escape helpers ---

def esc_py(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s


def esc_dq(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return s


def esc_js(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s


def esc_js_template(s):
    s = s.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    return '`%s`' % s


def esc_shell_sq(s):
    return "'%s'" % s.replace("'", "'\\''")


def esc_php_sq(s):
    s = s.replace('\\', '\\\\').replace("'", "\\'")
    return "'%s'" % s


def esc_rb(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t').replace('#', '\\#')
    return s


def esc_cs(s):
    return s.replace('"', '""')


def esc_java(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s


def esc_ps(s):
    return s.replace("'", "''")


def esc_rs(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return s


def esc_go_raw(s):
    if '`' not in s:
        return '`%s`' % s
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return '"%s"' % s


# --- Format converters ---

def convert_to_python(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = ["import requests", "", 'url = "%s"' % url]

    if headers:
        lines += ["", "headers = {"]
        for k, v in sorted(headers.items()):
            lines.append('    "%s": "%s",' % (esc_py(k), esc_py(v)))
        lines += ["}"]

    if cookies:
        lines += ["", "cookies = {"]
        for k, v in sorted(cookies.items()):
            lines.append('    "%s": "%s",' % (esc_py(k), esc_py(v)))
        lines += ["}"]

    body_arg = ""
    if body:
        if "json" in content_type:
            try:
                json_obj = json.loads(body)
                json_str = json.dumps(json_obj, indent=4)
                json_str = json_str.replace(': null', ': None').replace(': true', ': True').replace(': false', ': False')
                lines += ["", "json_body = %s" % json_str]
                body_arg = ", json=json_body"
            except (ValueError, TypeError):
                lines += ["", "data = '''%s'''" % body]
                body_arg = ", data=data"
        else:
            lines += ["", "data = '''%s'''" % body]
            body_arg = ", data=data"

    method_lower = method.lower()
    valid_methods = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    if method_lower in valid_methods:
        call = "requests.%s(url" % method_lower
    else:
        call = "requests.request('%s', url" % method

    kwargs = []
    if headers:
        kwargs.append("headers=headers")
    if cookies:
        kwargs.append("cookies=cookies")
    if body_arg:
        kwargs.append(body_arg.lstrip(", "))

    lines.append("")
    if kwargs:
        lines.append("response = %s, %s)" % (call, ", ".join(kwargs)))
    else:
        lines.append("response = %s)" % call)
    lines += ["", "print(response.status_code)", "print(response.text)"]

    return "\n".join(lines)


def convert_to_go(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']

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

    if body:
        lines.append('\tbody := strings.NewReader(%s)' % esc_go_raw(body))
    lines.append('\treq, _ := http.NewRequest("%s", "%s", %s)' % (
        method, url, "body" if body else "nil"))

    for k, v in sorted(headers.items()):
        lines.append('\treq.Header.Set("%s", "%s")' % (esc_dq(k), esc_dq(v)))
    for k, v in sorted(cookies.items()):
        lines.append('\treq.AddCookie(&http.Cookie{Name: "%s", Value: "%s"})' % (esc_dq(k), esc_dq(v)))

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
    return "\n".join(lines)


def convert_to_curl(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']

    parts = ['curl -s -X %s "%s"' % (method, url)]
    for k, v in sorted(headers.items()):
        parts.append('  -H "%s: %s"' % (k, esc_dq(v)))
    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        parts.append('  -H "Cookie: %s"' % cookie_str)
    if body:
        parts.append("  --data-raw %s" % esc_shell_sq(body))
    return " \\\n".join(parts)


def convert_to_fetch(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = [
        'const response = await fetch("%s", {' % url,
        '  method: "%s",' % method,
    ]

    if headers:
        lines += ["  headers: {"]
        for k, v in sorted(headers.items()):
            lines.append('    "%s": "%s",' % (esc_js(k), esc_js(v)))
        lines += ["},"]

    if body:
        if "json" in content_type:
            lines.append("  body: JSON.stringify(%s)," % body)
        else:
            lines.append("  body: %s," % esc_js_template(body))

    lines += ["});", "", "console.log(response.status);", "console.log(await response.text());"]
    return "\n".join(lines)


def convert_to_axios(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = [
        'const axios = require("axios");',
        '',
        'const response = await axios({',
        '  method: "%s".toLowerCase(),' % method,
        '  url: "%s",' % url,
    ]

    if headers:
        lines += ["  headers: {"]
        for k, v in sorted(headers.items()):
            lines.append('    "%s": "%s",' % (esc_js(k), esc_js(v)))
        lines += ["  },"]

    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        lines.append('  headers: { ...this?.headers, "Cookie": "%s" },' % esc_js(cookie_str))

    if body:
        if "json" in content_type:
            lines.append("  data: %s," % body)
        else:
            lines.append("  data: %s," % esc_js_template(body))

    lines += [
        "});",
        "",
        "console.log(response.status);",
        "console.log(response.data);",
    ]
    return "\n".join(lines)


def convert_to_php(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']

    lines = [
        '<?php', '',
        '$ch = curl_init();',
        'curl_setopt($ch, CURLOPT_URL, "%s");' % url,
        'curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "%s");' % method,
        'curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);',
    ]

    if headers:
        lines.append("$headers = [")
        for k, v in sorted(headers.items()):
            lines.append('    "%s: %s",' % (k, esc_dq(v)))
        lines += ["];", "curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);"]

    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        lines.append('curl_setopt($ch, CURLOPT_COOKIE, "%s");' % esc_dq(cookie_str))

    if body:
        lines.append("curl_setopt($ch, CURLOPT_POSTFIELDS, %s);" % esc_php_sq(body))

    lines += [
        '$response = curl_exec($ch);',
        '$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);',
        'curl_close($ch);', '',
        'echo $statusCode . "\\n";',
        'echo $response . "\\n";',
        '?>',
    ]
    return "\n".join(lines)


def convert_to_ruby(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = [
        'require "net/http"',
        'require "uri"',
        'require "json"',
        '',
        'uri = URI.parse("%s")' % url,
        '',
    ]

    method_class = method.capitalize()
    if method_class in ["Get", "Post", "Put", "Patch", "Delete", "Head", "Options"]:
        lines.append('request = Net::HTTP::%s.new(uri)' % method_class)
    else:
        lines.append('request = Net::HTTPGenericRequest.new("%s", true, nil, uri)' % method)

    for k, v in sorted(headers.items()):
        lines.append('request["%s"] = "%s"' % (esc_rb(k), esc_rb(v)))

    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        lines.append('request["Cookie"] = "%s"' % esc_rb(cookie_str))

    if body:
        if "json" in content_type:
            lines.append("request.body = %s.to_json" % body)
        else:
            lines.append('request.body = "%s"' % esc_rb(body))

    lines += [
        '',
        'response = Net::HTTP.start(uri.hostname, uri.port, :use_ssl => uri.scheme == "https") do |http|',
        '  http.request(request)',
        'end',
        '',
        'puts response.code',
        'puts response.body',
    ]
    return "\n".join(lines)


def convert_to_csharp(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

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

    if headers:
        for k, v in sorted(headers.items()):
            lines.append('        client.DefaultRequestHeaders.Add("%s", "%s");' % (esc_cs(k), esc_cs(v)))

    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        lines.append('        client.DefaultRequestHeaders.Add("Cookie", "%s");' % esc_cs(cookie_str))

    body_var = "null"
    if body:
        if "json" in content_type:
            lines.append('        var json = @"%s";' % esc_cs(body))
            lines.append('        var content = new StringContent(json, Encoding.UTF8, "application/json");')
            body_var = "content"
        else:
            lines.append('        var body = @"%s";' % esc_cs(body))
            lines.append('        var content = new StringContent(body, Encoding.UTF8, "%s");' % esc_cs(content_type))
            body_var = "content"

    lines += [
        '',
        '        var response = await client.%sAsync("%s", %s);' % (method.capitalize(), url, body_var),
        '        var responseBody = await response.Content.ReadAsStringAsync();',
        '',
        '        Console.WriteLine(response.StatusCode);',
        '        Console.WriteLine(responseBody);',
        '    }',
        '}',
    ]
    return "\n".join(lines)


def convert_to_java(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']

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

    header_lines = []
    for k, v in sorted(headers.items()):
        header_lines.append('                .header("%s", "%s")' % (esc_java(k), esc_java(v)))
    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        header_lines.append('                .header("Cookie", "%s")' % esc_java(cookie_str))

    if body:
        body_builder = '                .POST(HttpRequest.BodyPublishers.ofString("""\n                    %s\n                """))' % body
    elif method == "GET":
        body_builder = '                .GET()'
    else:
        body_builder = '                .method("%s", HttpRequest.BodyPublishers.noBody())' % method

    lines += [
        '        HttpRequest request = HttpRequest.newBuilder()',
        '                .uri(URI.create("%s"))' % url,
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
    return "\n".join(lines)


def convert_to_powershell(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = []

    if headers:
        lines.append("$headers = @{")
        for k, v in sorted(headers.items()):
            lines.append('    "%s" = "%s"' % (esc_ps(k), esc_ps(v)))
        lines += ["}", ""]

    if cookies:
        for k, v in sorted(cookies.items()):
            lines.append('$cookie_%s = New-Object System.Net.Cookie("%s", "%s", "/", $null)' % (esc_ps(k).replace('-', '_'), esc_ps(k), esc_ps(v)))
        lines.append("")

    if body:
        if "json" in content_type:
            lines.append("$body = @'")
            lines.append(body)
            lines += ["'@", ""]
        else:
            lines.append('$body = "%s"' % esc_ps(body))
            lines.append("")

    lines.append('$response = Invoke-RestMethod \\')
    lines.append('    -Method %s \\' % method)
    lines.append('    -Uri "%s" \\' % url)
    if headers:
        lines.append('    -Headers $headers \\')
    if body:
        lines.append('    -Body $body \\')

    lines += [
        "",
        'Write-Output $response',
    ]
    return "\n".join(lines)


def convert_to_rust(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']
    content_type = get_content_type(headers)

    lines = [
        'use std::collections::HashMap;',
        '',
        '#[tokio::main]',
        'async fn main() -> Result<(), Box<dyn std::error::Error>> {',
        '    let client = reqwest::Client::new();',
        '',
    ]

    method_lower = method.lower()
    valid_methods = ["get", "post", "put", "patch", "delete", "head"]
    if method_lower in valid_methods:
        call = "client.%s" % method_lower
    else:
        call = 'client.request(reqwest::Method::from_bytes(b"%s")?)' % method

    lines.append('    let mut request = %s("%s");' % (call, url))

    for k, v in sorted(headers.items()):
        lines.append('    request = request.header("%s", "%s");' % (esc_rs(k), esc_rs(v)))

    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        lines.append('    request = request.header("Cookie", "%s");' % esc_rs(cookie_str))

    if body:
        if "json" in content_type:
            lines.append("    request = request.json(&serde_json::json!(%s));" % body)
        else:
            lines.append('    request = request.body("%s");' % esc_rs(body))

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
    return "\n".join(lines)


def convert_to_wget(parsed):
    url = build_url(parsed)
    method = parsed['method']
    headers = parsed['headers']
    cookies = parsed['cookies']
    body = parsed['body']

    parts = ['wget -q -O -']
    if method != "GET":
        parts.append('--method=%s' % method)
    for k, v in sorted(headers.items()):
        parts.append('  --header="%s: %s"' % (k, esc_dq(v)))
    if cookies:
        cookie_str = "; ".join("%s=%s" % (k, v) for k, v in sorted(cookies.items()))
        parts.append('  --header="Cookie: %s"' % cookie_str)
    if body:
        parts.append('  --body-data=%s' % esc_shell_sq(body))
    parts.append('  "%s"' % url)
    return " \\\n".join(parts)


CONVERTERS = {
    "python": convert_to_python,
    "go": convert_to_go,
    "curl": convert_to_curl,
    "fetch": convert_to_fetch,
    "axios": convert_to_axios,
    "php": convert_to_php,
    "ruby": convert_to_ruby,
    "csharp": convert_to_csharp,
    "java": convert_to_java,
    "powershell": convert_to_powershell,
    "rust": convert_to_rust,
    "wget": convert_to_wget,
}


def main():
    parser = argparse.ArgumentParser(
        description='Convert HTTP request to code in multiple languages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats:
  python      Python (requests)
  go          Go (net/http)
  curl        cURL
  fetch       JavaScript (fetch)
  axios       JavaScript (axios)
  php         PHP (curl)
  ruby        Ruby (net/http)
  csharp      C# (HttpClient)
  java        Java (HttpClient)
  powershell  PowerShell (Invoke-RestMethod)
  rust        Rust (reqwest)
  wget        wget

Examples:
  %(prog)s --file request.txt --format python
  %(prog)s --file request.txt --format all
  %(prog)s --url https://example.com --format curl
  echo 'GET / HTTP/1.1\\r\\nHost: example.com' | %(prog)s --format go
        """,
    )
    parser.add_argument('--file', '-f', help='File containing raw HTTP request')
    parser.add_argument('--url', '-u', help='URL to convert (simple GET request)')
    parser.add_argument(
        '--format', '-F',
        default='python',
        help='Output format (default: python). Use "all" for all formats.',
    )
    args = parser.parse_args()

    if args.url:
        parsed = {
            'method': 'GET',
            'path': '/',
            'protocol': 'https',
            'host': args.url.replace('https://', '').replace('http://', '').split('/')[0],
            'port': 443,
            'headers': {},
            'cookies': {},
            'body': '',
        }
        if args.url.startswith('http://'):
            parsed['protocol'] = 'http'
            parsed['port'] = 80
    else:
        if args.file:
            with open(args.file, 'r') as f:
                raw_request = f.read()
        else:
            if sys.stdin.isatty():
                print("Enter raw HTTP request (Ctrl+D to finish):")
            raw_request = sys.stdin.read()

        if not raw_request.strip():
            print("Error: No input provided", file=sys.stderr)
            sys.exit(1)

        try:
            parsed = parse_raw_http_request(raw_request)
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr)
            sys.exit(1)

    fmt = args.format.lower()

    if fmt == "all":
        for name in SUPPORTED_FORMATS:
            print("=" * 60)
            print("  %s" % name.upper())
            print("=" * 60)
            print(CONVERTERS[name](parsed))
            print()
    elif fmt in CONVERTERS:
        print(CONVERTERS[fmt](parsed))
    else:
        print("Error: Unknown format '%s'" % fmt, file=sys.stderr)
        print("Supported: %s" % ", ".join(SUPPORTED_FORMATS), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
