from flask import Flask, render_template_string, send_file
import plistlib, subprocess, re
from zipfile import ZipFile, Path
from multiprocessing import Process, Queue
import time, os

url_pattern = re.compile(
    r'http[s]?://'
    r'(?:[a-zA-Z]|[0-9]|[$-_@.&+]|'
    r'[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

def tunnel(queue):
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
                queue.put(found_link)
        elif not process.poll():
            break

base_plist = {"items": []}
app_item = {
    "assets": [],
    "metadata": {}
}

software_package = {
    "kind": "software-package",
    "url": ""
}
display_image = {
    "kind": "display-image",
    "needs-shine": False,
    "url": ""
}
metadata = {
    "bundle-identifier": "org.company.app",
    "bundle-version": "1",
    "kind": "software",
    "title": "Unknown"
}


app = Flask(__name__)

@app.route("/download")
def download_app():
    return send_file("input.ipa", download_name="app.ipa")

@app.route("/icon.png")
def app_icon():
    return send_file("icon.png", download_name="image.png")

def rip_ipa_info():
    myzip = ZipFile("input.ipa")
    files = myzip.namelist()
    filter_info = [i for i in files if "Info.plist" in i]
    filter_proj = [i for i in filter_info if "lproj" not in i]

    complete_plist_data = {}

    for info_plist_path in [i for i in files if "plist" in i]:
        info_plist = myzip.read(info_plist_path)
        plist = plistlib.loads(info_plist)
        for k in plist:
            complete_plist_data[k] = plist[k]
    myzip.close()

    return {
        "bundle-identifier": complete_plist_data["CFBundleIdentifier"],
        "title": complete_plist_data["CFBundleName"],
        "version": complete_plist_data["CFBundleVersion"],
        "primary-icon":complete_plist_data["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"][0]
    }

def rip_ipa_images(primary_icon):
    myzip = ZipFile("input.ipa")
    files = myzip.namelist()
    filter_info = [i for i in files if ".png" in i]
    filter_icon = [i for i in filter_info if primary_icon.lower() in i.lower()]

    icon_path = filter_icon[0]
    image_bytes = myzip.read(icon_path)
    open("icon.png","wb").write(image_bytes)

    myzip.close()

def load_ipa():
    ipa_info = rip_ipa_info()
    rip_ipa_images(ipa_info['primary-icon'])
    metadata['bundle-identifier'] = ipa_info['bundle-identifier']
    metadata['title'] = ipa_info['title']
    metadata['version'] = ipa_info['version']

def save_app_plist(tunnel_url):
    software_package['url'] = tunnel_url.rstrip("/") + "/download"
    app_item['assets'].append(software_package)
    display_image['url'] = tunnel_url.rstrip("/") + "/icon.png"
    app_item['assets'].append(display_image)
    app_item['metadata'] = metadata
    base_plist['items'].append(app_item)
    plistlib.dump(base_plist, open("install.plist", "wb"))
    return tunnel_url.rstrip("/") + "/install.plist"

url_prefix = "itms-services://?action=download-manifest&url="
tunnel_url = ""

@app.route("/")
def install_homepage():
    return render_template_string('''
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
            <h1><a href="''' + url_prefix + tunnel_url.rstrip("/") + "/install.plist" + '''">Tap to install app</a></h1>
        </body>
    </html>
    ''')

def server():
    load_ipa()
    save_app_plist(tunnel_url)
    app.run(port=5500)

if __name__=="__main__":
    queue = Queue()
    tunnel_proc = Process(target=tunnel, args=(queue,))
    tunnel_proc.start()
    tunnel_url = queue.get()
    print(tunnel_url)
    os.system("open " + tunnel_url)

    server_process = Process(target=server)
    server_process.start()
    
    time.sleep(300)
    tunnel_proc.terminate()
    server_process.terminate()