from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

__USER_DATE_DIR_PATH__ = r"C:\Users\lemon\Desktop\Azalea\chrome_profile"
__EXECUTABLE_PATH__ = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class Browser:
    def __init__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch_persistent_context(
            user_data_dir=__USER_DATE_DIR_PATH__,
            executable_path=__EXECUTABLE_PATH__,
            accept_downloads=True,
            headless=False,
            bypass_csp=True,
            slow_mo=10,
            args=['--disable-blink-features=AutomationControlled']
        )

        self.page = self.browser.new_page()

    def search(self, query):
        url = (
            "https://cn.bing.com/search?q="
            + query.replace(" ", "+")
        )
        self.page.goto(url, timeout=30000)
        time.sleep(2)
        html = self.page.content()
        soup = BeautifulSoup(
            html,
            "html.parser"
        )
        results = []

        for a in soup.find_all("a"):
            href = a.get("href")
            text = a.get_text(
                " ",
                strip=True
            )
            if href and href.startswith("http"):  # type: ignore
                results.append({
                    "title": text,
                    "url": href
                })
        return results[:10]

    def open(self, url):
        self.page.goto(
            url,
            timeout=30000
        )
        time.sleep(2)
        return self.read()

    def read(self):
        html = self.page.content()
        soup = BeautifulSoup(
            html,
            "html.parser"
        )
        for tag in soup(
            ["script",
             "style",
             "nav",
             "footer"]
        ):
            tag.decompose()
        text = soup.get_text(
            "\n",
            strip=True
        )
        return text[:8000]


browser = Browser()
