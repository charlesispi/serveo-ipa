from zipfile import ZipFile
import plistlib


class ipaPackager():
    def __init__(self):
        self.base_plist = {"items": []}
        self.app_item = {
            "assets": [],
            "metadata": {}
        }

        self.software_package = {
            "kind": "software-package",
            "url": ""
        }
        self.display_image = {
            "kind": "display-image",
            "needs-shine": False,
            "url": ""
        }
        self.metadata = {
            "bundle-identifier": "org.company.app",
            "bundle-version": "1",
            "kind": "software",
            "title": "Unknown"
        }
        self.signed = False

    def rip_ipa_info(self):
        myzip = ZipFile("input.ipa")
        files = myzip.namelist()
        filter_info = [i for i in files if "Info.plist" in i]
        filter_bundle = [i for i in filter_info if ".bundle" not in i]
        filter_framework = [i for i in filter_bundle if ".framework" not in i]

        complete_plist_data = {}

        for info_plist_path in filter_framework:
            info_plist = myzip.read(info_plist_path)
            plist = plistlib.loads(info_plist)
            for k in plist:
                complete_plist_data[k] = plist[k]
        myzip.close()

        code_sign_folder = [i for i in files if "_CodeSignature" in i]
        signed = len(code_sign_folder) > 0

        return {
            "bundle-identifier": complete_plist_data.get("CFBundleIdentifier", "com.default.default"),
            "title": complete_plist_data.get("CFBundleName", "Unknown"),
            "version": complete_plist_data.get("CFBundleVersion", "1"),
            "primary-icon": complete_plist_data["CFBundleIcons"]["CFBundlePrimaryIcon"]["CFBundleIconFiles"][0],
            "signed": signed
        }

    def rip_ipa_images(self, primary_icon):
        myzip = ZipFile("input.ipa")
        files = myzip.namelist()
        filter_info = [i for i in files if ".png" in i]
        filter_icon = [i for i in filter_info if primary_icon.lower() in i.lower()]

        icon_path = filter_icon[0]
        image_bytes = myzip.read(icon_path)
        open("icon.png","wb").write(image_bytes)

        myzip.close()

    def load_ipa(self):
        ipa_info = self.rip_ipa_info()
        self.signed = ipa_info["signed"]
        self.rip_ipa_images(ipa_info['primary-icon'])
        self.metadata['bundle-identifier'] = ipa_info['bundle-identifier']
        self.metadata['title'] = ipa_info['title']
        self.metadata['version'] = ipa_info['version']

    def save_app_plist(self, tunnel_url):
        self.software_package['url'] = tunnel_url.rstrip("/") + "/download"
        self.app_item['assets'].append(self.software_package)
        self.display_image['url'] = tunnel_url.rstrip("/") + "/icon.png"
        self.app_item['assets'].append(self.display_image)
        self.app_item['metadata'] = self.metadata
        self.base_plist['items'].append(self.app_item)
        plistlib.dump(self.base_plist, open("install.plist", "wb"))
        return tunnel_url.rstrip("/") + "/install.plist"