import os
import sys
import ssl
import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import zipfile
import hashlib

# Configure SSL context
ctx = ssl._create_unverified_context()
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
HEADERS = {'User-Agent': USER_AGENT}

SITE_ROOT = 'https://www.villatiflis.com'
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORKSPACE, 'villatiflis')
os.makedirs(OUTPUT_DIR, exist_ok=True)

PAGES = [
    ('/', 'index.html'),
    ('/about-us/', 'about-us/index.html'),
    ('/bed-breakfast/', 'bed-breakfast/index.html'),
    ('/contact/', 'contact/index.html'),
    ('/disclaimer-impressum/', 'disclaimer-impressum/index.html'),
    ('/guestbook/', 'guestbook/index.html'),
    ('/links/', 'links/index.html'),
    ('/mountains-wine/', 'mountains-wine/index.html'),
    ('/prices-reservations/', 'prices-reservations/index.html'),
    ('/sitemap/', 'sitemap/index.html'),
    ('/slide-show/', 'slide-show/index.html'),
    ('/sports-activities/', 'sports-activities/index.html'),
    ('/tbilisi/', 'tbilisi/index.html'),
]

PAGE_MAP = {path: rel for path, rel in PAGES}

ASSETS_DIR = os.path.join(OUTPUT_DIR, 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)

url_to_local = {}
downloaded_content = {}

def get_filename_for_url(url):
    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path
    ext = os.path.splitext(clean_path)[1].lower()
    if not ext or len(ext) > 5:
        if 'css' in clean_path:
            ext = '.css'
        elif 'js' in clean_path:
            ext = '.js'
        elif 'jpg' in clean_path or 'jpeg' in clean_path:
            ext = '.jpg'
        elif 'png' in clean_path:
            ext = '.png'
        elif 'gif' in clean_path:
            ext = '.gif'
        elif 'svg' in clean_path:
            ext = '.svg'
        else:
            ext = '.dat'
    
    base_name = os.path.basename(clean_path)
    base_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base_name)
    if not base_name or base_name == ext:
        base_name = 'resource'
    
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
    root_name = os.path.splitext(base_name)[0][:30]
    final_name = f"{root_name}_{url_hash}{ext}"
    return final_name

def download_url(url):
    if url in downloaded_content:
        return downloaded_content[url]
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = resp.read()
            downloaded_content[url] = data
            return data
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None

def download_and_save_asset(url, subfolder=''):
    if url in url_to_local:
        return url_to_local[url]
    
    fname = get_filename_for_url(url)
    target_rel = os.path.join('assets', subfolder, fname) if subfolder else os.path.join('assets', fname)
    target_rel = target_rel.replace('\\', '/')
    target_abs = os.path.join(OUTPUT_DIR, target_rel)
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    
    data = download_url(url)
    if data is None:
        return None
    
    parsed_path = urllib.parse.urlparse(url).path.lower()
    is_css = parsed_path.endswith('.css') or 'css' in parsed_path
    
    if is_css:
        try:
            css_text = data.decode('utf-8', errors='ignore')
            def replace_css_url(match):
                raw_ref = match.group(1).strip('\'" ')
                if raw_ref.startswith('data:') or not raw_ref:
                    return match.group(0)
                ref_url = urllib.parse.urljoin(url, raw_ref)
                saved_asset_rel = download_and_save_asset(ref_url, subfolder='css_res')
                if saved_asset_rel:
                    css_dir = os.path.dirname(target_rel)
                    rel_to_asset = os.path.relpath(saved_asset_rel, css_dir).replace('\\', '/')
                    return f'url("{rel_to_asset}")'
                return match.group(0)
            
            css_text_fixed = re.sub(r'url\s*\(\s*([^\)]+)\s*\)', replace_css_url, css_text)
            data = css_text_fixed.encode('utf-8')
        except Exception as e:
            print(f"Error processing CSS {url}: {e}")
    
    with open(target_abs, 'wb') as f:
        f.write(data)
    
    url_to_local[url] = target_rel
    print(f"Saved asset: {url} -> {target_rel}")
    return target_rel

def main():
    print("=== Step 1: Downloading all HTML pages ===")
    raw_pages = {}
    for path, rel_dest in PAGES:
        page_url = urllib.parse.urljoin(SITE_ROOT, path)
        print(f"Fetching {page_url} ...")
        html_data = download_url(page_url)
        if html_data:
            raw_pages[path] = (rel_dest, html_data.decode('utf-8', errors='ignore'))
        else:
            print(f"ERROR: Could not fetch {page_url}")

    print("\n=== Step 2: Extracting and downloading all assets ===")
    for path, (rel_dest, html_str) in raw_pages.items():
        base_url = urllib.parse.urljoin(SITE_ROOT, path)
        soup = BeautifulSoup(html_str, 'html.parser')
        
        # 1. Stylesheets
        for link in soup.find_all('link'):
            href = link.get('href')
            if href:
                full_url = urllib.parse.urljoin(base_url, href)
                if link.get('rel') == ['stylesheet'] or 'css' in href or 'favicon' in str(link.get('rel')):
                    download_and_save_asset(full_url, subfolder='css' if 'css' in href else 'img')
        
        # 2. Scripts
        for s in soup.find_all('script'):
            src = s.get('src')
            if src:
                full_url = urllib.parse.urljoin(base_url, src)
                download_and_save_asset(full_url, subfolder='js')
        
        # 3. Images and sources
        for img in soup.find_all(['img', 'source']):
            for attr in ['src', 'data-src', 'srcset']:
                val = img.get(attr)
                if val:
                    full_url = urllib.parse.urljoin(base_url, val)
                    download_and_save_asset(full_url, subfolder='img')
        
        # 4. Links to images / media
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urllib.parse.urljoin(base_url, href)
            p = urllib.parse.urlparse(full_url).path.lower()
            if any(p.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.pdf', '.webp']) or '/s/cc_images/' in full_url:
                download_and_save_asset(full_url, subfolder='img')
        
        # 5. Inline styles
        for tag in soup.find_all(style=True):
            style_str = tag['style']
            for m in re.findall(r'url\s*\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', style_str):
                if not m.startswith('data:'):
                    full_url = urllib.parse.urljoin(base_url, m)
                    download_and_save_asset(full_url, subfolder='img')
        
        for style in soup.find_all('style'):
            for m in re.findall(r'url\s*\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', style.text):
                if not m.startswith('data:'):
                    full_url = urllib.parse.urljoin(base_url, m)
                    download_and_save_asset(full_url, subfolder='img')

    # Also check emotionheader image
    emotion_url = "https://www.villatiflis.com/s/img/emotionheader.jpg"
    download_and_save_asset(emotion_url, subfolder='img')

    print("\n=== Step 3: Rewriting and saving all HTML pages for offline use ===")
    for path, (rel_dest, html_str) in raw_pages.items():
        base_url = urllib.parse.urljoin(SITE_ROOT, path)
        page_dir = os.path.dirname(rel_dest)
        soup = BeautifulSoup(html_str, 'html.parser')
        
        def to_rel(asset_target_rel):
            if not asset_target_rel:
                return None
            return os.path.relpath(asset_target_rel, page_dir if page_dir else '.').replace('\\', '/')

        # Rewrite links to other pages
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            full_url = urllib.parse.urljoin(base_url, href)
            parsed = urllib.parse.urlparse(full_url)
            
            if parsed.netloc in ('www.villatiflis.com', 'villatiflis.com'):
                norm_path = parsed.path
                if not norm_path.endswith('/') and '.' not in norm_path:
                    norm_path += '/'
                if norm_path in PAGE_MAP:
                    dest_page = PAGE_MAP[norm_path]
                    a['href'] = to_rel(dest_page)
                    continue
            
            if full_url in url_to_local:
                a['href'] = to_rel(url_to_local[full_url])

        # Rewrite stylesheets & favicons
        for link in soup.find_all('link'):
            href = link.get('href')
            if href:
                full_url = urllib.parse.urljoin(base_url, href)
                if full_url in url_to_local:
                    link['href'] = to_rel(url_to_local[full_url])

        # Rewrite script tags
        for s in soup.find_all('script'):
            src = s.get('src')
            if src:
                full_url = urllib.parse.urljoin(base_url, src)
                if full_url in url_to_local:
                    s['src'] = to_rel(url_to_local[full_url])

        # Rewrite images
        for img in soup.find_all(['img', 'source']):
            for attr in ['src', 'data-src']:
                val = img.get(attr)
                if val:
                    full_url = urllib.parse.urljoin(base_url, val)
                    if full_url in url_to_local:
                        img[attr] = to_rel(url_to_local[full_url])

        # Rewrite inline style attributes
        for tag in soup.find_all(style=True):
            def repl_style_url(match):
                raw = match.group(1).strip('\'" ')
                if raw.startswith('data:'):
                    return match.group(0)
                full_url = urllib.parse.urljoin(base_url, raw)
                if full_url in url_to_local:
                    return f'url("{to_rel(url_to_local[full_url])}")'
                return match.group(0)
            tag['style'] = re.sub(r'url\s*\(\s*([^\)]+)\s*\)', repl_style_url, tag['style'])

        # Rewrite <style> blocks
        for style in soup.find_all('style'):
            def repl_css_url(match):
                raw = match.group(1).strip('\'" ')
                if raw.startswith('data:'):
                    return match.group(0)
                full_url = urllib.parse.urljoin(base_url, raw)
                if full_url in url_to_local:
                    return f'url("{to_rel(url_to_local[full_url])}")'
                return match.group(0)
            style.string = re.sub(r'url\s*\(\s*([^\)]+)\s*\)', repl_css_url, style.text)
        
        target_html_abs = os.path.join(OUTPUT_DIR, rel_dest)
        os.makedirs(os.path.dirname(target_html_abs), exist_ok=True)
        with open(target_html_abs, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        print(f"Saved offline page: {rel_dest}")

    print("\n=== Step 4: Creating ZIP archive ===")
    zip_path = os.path.join(OUTPUT_DIR, 'villatiflis_complete_backup.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for file in files:
                if file.endswith('.zip'):
                    continue
                abs_f = os.path.join(root, file)
                rel_f = os.path.relpath(abs_f, OUTPUT_DIR)
                zf.write(abs_f, rel_f)
    print(f"Backup archive created at: {zip_path}")
    print("Done!")

if __name__ == '__main__':
    main()
