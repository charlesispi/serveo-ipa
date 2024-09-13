from flask import Flask, render_template_string, send_file, after_this_request, Response, request, abort
import subprocess, re
import time, os
import threading
from ipa_packager import ipaPackager
import queue

url_pattern = re.compile(
    r'http[s]?://'
    r'(?:[a-zA-Z]|[0-9]|[$-_@.&+]|'
    r'[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

def tunnel():
    ssh_command = "ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:5500 serveo.net"
    found_link = None

    process = subprocess.Popen(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    while True:
        next_line = process.stdout.readline()
        if next_line:
            line_text = next_line.decode("utf-8")
            links = url_pattern.findall(line_text)
            if links != [] and found_link == None:
                found_link = links[0]
                url_queue.put(found_link)
        elif not process.poll():
            break

app = Flask(__name__)

def generate_file(file_path):
    global total_downloaded_bytes
    with open(file_path, 'rb') as f:
        while chunk := f.read(4096):
            total_downloaded_bytes += len(chunk)
            yield chunk

def generate_partial_file(file_path, start, end):
    global total_downloaded_bytes
    with open(file_path, 'rb') as f:
        f.seek(start)
        chunk = f.read(min(4096, end - start))
        while start < end and chunk:
            start += len(chunk)
            total_downloaded_bytes += len(chunk)
            yield chunk

@app.route('/download', methods=['HEAD'])
def head():
    file_path = 'input.ipa'
    response = send_file(file_path, download_name="app.ipa")
    file_size = os.path.getsize(file_path)
    response.headers["Content-Length"] = str(file_size)
    return response

total_downloaded_bytes = 0
file_size = 1

@app.route("/download", methods=['GET'])
def download_app():
    print(request.headers)
    '''
    response = send_file("input.ipa", download_name="app.ipa")
    @response.call_on_close
    def shutdown_server(response):
        print("hello")
        shutdown()s
        print(response)
        return response
    return response'''
    
    file_path = 'input.ipa'
    global file_size
    file_size = os.path.getsize(file_path)
    last_modified_time = os.path.getmtime(file_path)
    last_modified_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified_time))
    etag = f'"{last_modified_time}-{file_size}-{hash(file_path)}"'

    range_header = request.headers.get('Range')

    if range_header:
        byte_range = range_header.strip().split('=')[1]
        start, end = byte_range.split('-')
        start = int(start)
        end = int(end) if end else file_size - 1

        print(start)
        print(end)

        if start > file_size or end >= file_size:
            abort(416)

        response = Response(
            generate_partial_file(file_path, start, end + 1),
            content_type='application/x-itunes-ipa'
        )
        response.headers["Content-Disposition"] = 'attachment; filename=app.ipa'
        response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        #response.headers["Content-Length"] = start - end
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers["Last-Modified"] = last_modified_str
        response.headers["ETag"] = etag
        response.status_code = 206
    else:
        global total_downloaded_bytes
        total_downloaded_bytes = 0
        response = Response(generate_file(file_path), content_type='application/x-itunes-ipa')
        response.headers["Content-Disposition"] = 'attachment; filename=app.ipa'
        response.headers["Content-Length"] = str(file_size)
        response.headers["Last-Modified"] = last_modified_str
        response.headers["ETag"] = etag

    return response

@app.route("/icon.png")
def app_icon():
    return send_file("icon.png", download_name="image.png")

url_prefix = "itms-services://?action=download-manifest&url="
tunnel_url = ""

def shutdown():
    os._exit(0)

@app.route("/") #packager
def install_homepage():
    template = '''
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!DOCTYPE html>
    <html>
        <head>
            <title>Install App</title>
            <style> 
                body {
                    text-align: center;
                }
                a {
                    text-decoration: none!important;
                }
            </style>
        </head>
        <body>
            <h1><a href="{{ url }}">Tap to install app</a></h1>
            {% if not packager.signed %}<h3>Fyi, this ipa didn't look like it was signed. It most likely won't work.</h3>{% endif %}
        </body>
    </html>
    '''
    return render_template_string(template, url=(url_prefix + tunnel_url.rstrip("/") + "/install.plist"), packager=packager)

@app.route("/install.plist")
def install_plist():
    return send_file("install.plist")

packager = ipaPackager()
url_queue = queue.Queue()

def track_download():
    global total_downloaded_bytes
    global file_size
    while True:
        percentage = total_downloaded_bytes / file_size
        time.sleep(0.5)
        if percentage > 0.99:
            break
    time.sleep(5)
    shutdown()

if __name__=="__main__":
    tunnel_proc = threading.Thread(target=tunnel)
    tunnel_proc.start()

    tunnel_url = url_queue.get()
    print(tunnel_url)
    os.system("open " + tunnel_url)

    download_tracking = threading.Thread(target=track_download)
    download_tracking.start()

    packager.load_ipa()
    packager.save_app_plist(tunnel_url)
    try:
        app.run(port=5500, host="127.0.0.1")
        #app.run(port=5500, host="0.0.0.0")
    except KeyboardInterrupt:
        shutdown()