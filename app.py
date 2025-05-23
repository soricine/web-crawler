from flask import Flask, request, jsonify, send_from_directory, render_template, Response
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin, urlparse
from pathlib import Path

app = Flask(__name__)
CORS(app)

MAX_PAGES = 3  # Limit crawling depth


def get_download_folder():
    """Return the path to the system's Downloads folder."""
    return str(Path.home() / "Downloads")

from flask import send_from_directory



def is_valid_internal_link(base_url, link):
    """Check if the link is a valid internal page (same domain, not external)."""
    base_domain = urlparse(base_url).netloc
    link_domain = urlparse(link).netloc
    return base_domain == link_domain and link.startswith("http")


def fetch_page_content(url, domain_folder):
    """Fetch page content, extract text, images, and internal links."""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract structured content
        page_content = {}
        for tag in ["h1", "h2", "h3", "p", "a", "li"]:
            elements = soup.find_all(tag)
            page_content[tag] = [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]

        # Extract images and download them
        image_urls = []
        img_folder = os.path.join(domain_folder, "images")
        os.makedirs(img_folder, exist_ok=True)

        for img_tag in soup.find_all("img", src=True):
            img_url = urljoin(url, img_tag["src"])
            img_filename = os.path.basename(urlparse(img_url).path)

            if img_filename:
                img_path = os.path.join(img_folder, img_filename)
                try:
                    img_data = requests.get(img_url, timeout=5).content
                    with open(img_path, 'wb') as img_file:
                        img_file.write(img_data)
                    image_urls.append(f"/download-images?domain={urlparse(url).netloc}&filename={img_filename}")
                except Exception as e:
                    print(f"Failed to download {img_url}: {e}")

        # Extract internal links
        links = set()
        for a_tag in soup.find_all("a", href=True):
            absolute_url = urljoin(url, a_tag["href"])
            if is_valid_internal_link(url, absolute_url):
                links.add(absolute_url)

        return {
            "url": url,
            "title": soup.title.string if soup.title else "No title found",
            "content": page_content,
            "images": image_urls,
            "links": list(links)
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


def crawl_website(start_url, max_pages=MAX_PAGES):
    """Crawls a website recursively, following internal links."""
    visited = set()
    to_visit = [start_url]
    all_results = []
    all_content = []

    domain_folder = os.path.join(get_download_folder(), urlparse(start_url).netloc)
    os.makedirs(domain_folder, exist_ok=True)

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue

        print(f"Crawling: {url} ...")
        result = fetch_page_content(url, domain_folder)

        all_results.append({"url": result["url"], "title": result.get("title", "No title")})
        all_content.append(result)

        visited.add(url)

        # Add new links to the queue
        new_links = [link for link in result.get("links", []) if link not in visited and len(visited) < max_pages]
        to_visit.extend(new_links)

        time.sleep(1)  # Prevent overloading the server

    # Save JSON files
    save_to_json(domain_folder, "site-urls.json", all_results)
    save_to_json(domain_folder, "site-content.json", all_content)

    return all_results
    




def save_to_json(folder, filename, data):
    """Save data to a JSON file inside the domain folder."""
    file_path = os.path.join(folder, filename)
    os.makedirs(folder, exist_ok=True)  # Ensure the folder exists
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)

def lightweight_crawl(start_url, max_pages=MAX_PAGES):
    """Crawls for preview purposes only, does not save or download files."""
    visited = set()
    to_visit = [start_url]
    all_results = []

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue

        print(f"[Preview Crawl] Visiting: {url}")
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "No title found"
            all_results.append({"url": url, "title": title})

            visited.add(url)

            # Extract internal links
            links = set()
            for a_tag in soup.find_all("a", href=True):
                absolute_url = urljoin(url, a_tag["href"])
                if is_valid_internal_link(url, absolute_url):
                    links.add(absolute_url)
            to_visit.extend([link for link in links if link not in visited])
            time.sleep(0.5)
        except Exception as e:
            all_results.append({"url": url, "error": str(e)})
            continue

    return all_results
@app.route('/')
def home():
    """Serve the index.html page."""
    return render_template('index.html')

@app.route('/test', methods=['GET'])
def test_connection():
    """Test the API connection."""
    return jsonify({"status": "API is working"})

from flask import Response, jsonify

@app.route('/crawl', methods=['POST'])
def crawl():
    """Start crawling and return results."""
    data = request.get_json()
    domain = data.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'No domain provided'}), 400

    if not domain.startswith('http'):
        domain = 'https://' + domain

        

    # Perform actual crawling instead of just lightweight crawl
    try:
        results = crawl_website(domain)  # Use the full crawl function
        return jsonify({"message": "Crawling complete", "pages_crawled": len(results)})
    except Exception as e:
        print(f"Error during crawling: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get-json', methods=['GET'])
def get_results_json():
    """Return the crawled URLs & titles as JSON."""
    domain = request.args.get('domain', '').strip()
    if not domain:
        return jsonify({'error': 'No domain provided'}), 400

    domain_folder = os.path.join(get_download_folder(), urlparse(domain).netloc)
    file_path = os.path.join(domain_folder, "site-urls.json")

    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return jsonify(json.load(file))

    return jsonify([]), 200


@app.route('/get-content', methods=['GET'])
def get_content_json():
    """Return the full page content structured by tags."""
    domain = request.args.get('domain', '').strip()
    if not domain:
        return jsonify({'error': 'No domain provided'}), 400

    domain_folder = os.path.join(get_download_folder(), urlparse(domain).netloc)
    file_path = os.path.join(domain_folder, "site-content.json")

    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return jsonify(json.load(file))

    return jsonify([]), 200


@app.route('/download-images', methods=['GET'])
def download_images():
    """Serve downloaded images."""
    domain = request.args.get('domain', '').strip()
    filename = request.args.get('filename', '').strip()

    if not domain or not filename:
        return jsonify({'error': 'Domain and filename required'}), 400

    domain_folder = os.path.join(get_download_folder(), domain, "images")
    file_path = os.path.join(domain_folder, filename)

    if os.path.exists(file_path):
        return send_from_directory(domain_folder, filename)

    return jsonify({'error': 'File not found'}), 404

@app.route('/preview-crawl', methods=['POST'])
def preview_crawl():
    """Only crawl and return URL titles, don't download anything."""
    data = request.get_json()
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({'error': 'No domain provided'}), 400

    if not domain.startswith('http'):
        domain = 'https://' + domain

    results = lightweight_crawl(domain)
    return jsonify({"message": "Preview crawl complete", "pages_crawled": len(results)})

@app.route('/serve-page', methods=['GET'])
def serve_page():
    """Serves the first crawled page as an HTML page with dynamic styling."""
    domain = request.args.get('domain', '').strip()
    style_option = request.args.get('style', '1')  # Default to style 1

    if not domain:
        return "No domain provided", 400

    domain_folder = os.path.join(get_download_folder(), urlparse(domain).netloc)
    file_path = os.path.join(domain_folder, "site-content.json")

    if not os.path.exists(file_path):
        return "Crawled data not found", 404

    with open(file_path, 'r') as file:
        data = json.load(file)

    if not data or not isinstance(data, list) or 'content' not in data[0]:
        return "No valid content found", 404

    # Extract content from JSON
    page_data = data[0]
    title = page_data.get("title", "Untitled Page")
    content = page_data["content"]

    # Define CSS styles based on the selected option
    if style_option == "2":  # Dark Theme
        css = """
        body {
            font-family: Arial, sans-serif;
            background: #121212;
            color: #f1f1f1;
            padding: 20px;
            line-height: 1.6;
            transition: all 0.3s ease-in-out;
        }
        h1, h2, h3 {
            color: #00c6ff;
            margin-bottom: 15px;
        }
        p {
            margin-bottom: 10px;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 10px 0;
            border-radius: 8px;
            display: block;
            box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        img:hover {
            transform: scale(1.05);
            box-shadow: 0px 6px 10px rgba(0, 0, 0, 0.5);
        }
        ul, ol {
            margin: 10px 0;
            padding-left: 20px;
        }
        li {
            margin-bottom: 5px;
        }
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            h1 {
                font-size: 24px;
            }
            h2 {
                font-size: 20px;
            }
            h3 {
                font-size: 18px;
            }
            p {
                font-size: 14px;
            }
        }
        @media (max-width: 480px) {
            h1 {
                font-size: 20px;
            }
            h2 {
                font-size: 18px;
            }
            h3 {
                font-size: 16px;
            }
            p {
                font-size: 12px;
            }
        }
        """
    elif style_option == "3":  # Serif Theme
        css = """
        body {
            font-family: Georgia, serif;
            background: #fff8f0;
            color: #3b2f2f;
            padding: 20px;
            line-height: 1.8;
            transition: all 0.3s ease-in-out;
        }
        h1, h2, h3 {
            color: #964B00;
            margin-bottom: 15px;
        }
        p {
            margin-bottom: 10px;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            display: block;
        }
        ul, ol {
            margin: 10px 0;
            padding-left: 20px;
        }
        li {
            margin-bottom: 5px;
        }
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            h1 {
                font-size: 24px;
            }
            h2 {
                font-size: 20px;
            }
            h3 {
                font-size: 18px;
            }
            p {
                font-size: 14px;
            }
        }
        @media (max-width: 480px) {
            h1 {
                font-size: 20px;
            }
            h2 {
                font-size: 18px;
            }
            h3 {
                font-size: 16px;
            }
            p {
                font-size: 12px;
            }
        }
        """
    else:  # Default Theme
        css = """
        body {
            font-family: Arial, sans-serif;
            background: #f9f9f9;
            color: #333;
            padding: 20px;
            line-height: 1.6;
            transition: all 0.3s ease-in-out;
        }
        h1, h2, h3 {
            color: #007BFF;
            margin-bottom: 15px;
        }
        p {
            margin-bottom: 10px;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 10px 0;
            border-radius: 8px;
            display: block;
            box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        img:hover {
            transform: scale(1.05);
            box-shadow: 0px 6px 10px rgba(0, 0, 0, 0.2);
        }
        ul, ol {
            margin: 10px 0;
            padding-left: 20px;
        }
        li {
            margin-bottom: 5px;
        }
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            h1 {
                font-size: 24px;
            }
            h2 {
                font-size: 20px;
            }
            h3 {
                font-size: 18px;
            }
            p {
                font-size: 14px;
            }
        }
        @media (max-width: 480px) {
            h1 {
                font-size: 20px;
            }
            h2 {
                font-size: 18px;
            }
            h3 {
                font-size: 16px;
            }
            p {
                font-size: 12px;
            }
        }
        """

    # Generate the HTML content with the selected CSS
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title}</title>
        <style>{css}</style>
    </head>
    <body>
        <h1>{title}</h1>
        {''.join(f"<h2>{h}</h2>" for h in content.get("h2", []))}
        {''.join(f"<h3>{h}</h3>" for h in content.get("h3", []))}
        {''.join(f"<p>{p}</p>" for p in content.get("p", []))}
        {''.join(f"<li>{li}</li>" for li in content.get("li", []))}
        {''.join(f'<img src="{img}" alt="Image">' for img in page_data.get("images", []))}
    </body>
    </html>
    """
    return html_content

if __name__ == '__main__':
    app.run(debug=True)
