from playwright.sync_api import sync_playwright
import os

p = sync_playwright().start()
ctx = p.chromium.launch_persistent_context(user_data_dir=os.path.join(os.getcwd(), 'browser_session'))
cookies = ctx.cookies()
cookie_string = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
print(len(cookie_string))
ctx.close()
p.stop()
