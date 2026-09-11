import urllib.request
import re

url = 'https://nl-to-dashboard.vercel.app'
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    js_files = re.findall(r'src=\"(/_next/static/chunks/app/page-[^\"]+\.js)\"', html)
    if js_files:
        js_url = url + js_files[0]
        js_code = urllib.request.urlopen(urllib.request.Request(js_url, headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')
        api_urls = re.findall(r'https?://[^\s\"\'`]+', js_code)
        api_urls = [u for u in api_urls if 'api' in u or 'render' in u]
        print('Found API URLs in bundled JS:', list(set(api_urls)))
    else:
        print('No page.js found in HTML')
except Exception as e:
    print('Error:', e)
