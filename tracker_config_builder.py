#!/usr/bin/env python3

"""
TrackerAutoLogin tracker_config.json generator

Features:
- FlareSolverr integration
- FlareSolverr cookie handoff to Selenium
- Selenium fallback
- Automatic selector generation
- Existing tracker_config.json merging
- Debug output
"""


import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path


import requests

from bs4 import BeautifulSoup


from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait



# ============================================================
# Configuration
# ============================================================


# Enable/disable FlareSolverr
FLARESOLVERR_ENABLED = True

# Your current FlareSolverr instance
# Change this only if the server changes
FLARESOLVERR_IP = "172.0.0.1"
FLARESOLVERR_PORT = "8191"
FLARESOLVERR_URL = "http://"+FLARESOLVERR_IP+":"FLARESOLVERR_PORT

# Maximum time FlareSolverr is allowed
FLARESOLVERR_TIMEOUT = 120

# Selenium timeout
SELENIUM_TIMEOUT = 30



# Output config
DEFAULT_CONFIG_FILE = (
    "tracker_config.json"
)



# Debug output directory
DEBUG_DIR = Path(
    "debug"
)



DEBUG_DIR.mkdir(
    exist_ok=True
)



logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "[%(levelname)s] "
        "%(message)s"
    )
)





# ============================================================
# Tracker extractor
# ============================================================


class TrackerExtractor:


    USERNAME_HINTS = [
        "username",
        "user",
        "login",
        "email",
        "mail"
    ]


    PASSWORD_HINTS = [
        "password",
        "passwd",
        "pass"
    ]


    SUBMIT_HINTS = [
        "login",
        "log in",
        "sign in",
        "submit"
    ]



    def __init__(
        self,
        url,
        timeout=SELENIUM_TIMEOUT
    ):

        self.url = url
        self.timeout = timeout


        self.selenium = None



    # --------------------------------------------------------
    # Selenium
    # --------------------------------------------------------


    def create_driver(self):

        options = Options()


        options.add_argument(
            "--headless=new"
        )


        options.add_argument(
            "--disable-gpu"
        )


        options.add_argument(
            "--no-sandbox"
        )


        options.add_argument(
            "--disable-dev-shm-usage"
        )


        options.add_argument(
            "--window-size=1920,1080"
        )


        return webdriver.Chrome(
            options=options
        )



    # --------------------------------------------------------
    # FlareSolverr
    # --------------------------------------------------------


    def flaresolverr(self):

        if not FLARESOLVERR_ENABLED:

            return None



        logging.info(
            "Requesting page through FlareSolverr"
        )


        payload = {

            "cmd":
            "request.get",


            "url":
            self.url,


            "maxTimeout":
            FLARESOLVERR_TIMEOUT * 1000

        }



        try:

            response = requests.post(

                f"{FLARESOLVERR_URL}/v1",

                json=payload,

                timeout=FLARESOLVERR_TIMEOUT

            )


            response.raise_for_status()


            data = response.json()



            if data.get(
                "status"
            ) != "ok":

                logging.warning(
                    "FlareSolverr returned failure"
                )

                return None



            solution = data.get(
                "solution",
                {}
            )



            return {

                "html":
                solution.get(
                    "response",
                    ""
                ),


                "url":
                solution.get(
                    "url",
                    self.url
                ),


                "title":
                solution.get(
                    "title",
                    ""
                ),


                "cookies":
                solution.get(
                    "cookies",
                    []
                )

            }



        except Exception as exc:


            logging.warning(
                "FlareSolverr failed: %s",
                exc
            )


            return None




    # --------------------------------------------------------
    # Cookie transfer
    # --------------------------------------------------------


    def add_cookies_to_selenium(
        self,
        cookies
    ):

        if not cookies:

            return



        logging.info(
            "Injecting %s cookies into Selenium",
            len(cookies)
        )


        self.selenium.get(
            self.url
        )


        for cookie in cookies:


            try:

                selenium_cookie = {

                    "name":
                    cookie["name"],


                    "value":
                    cookie["value"]

                }



                if cookie.get(
                    "domain"
                ):

                    selenium_cookie[
                        "domain"
                    ] = cookie["domain"]



                if cookie.get(
                    "path"
                ):

                    selenium_cookie[
                        "path"
                    ] = cookie["path"]



                self.selenium.add_cookie(
                    selenium_cookie
                )



            except Exception as exc:

                logging.debug(
                    "Cookie skipped: %s",
                    exc
                )



        self.selenium.refresh()




    # --------------------------------------------------------
    # Selenium page load
    # --------------------------------------------------------


    def selenium_load(self):


        logging.info(
            "Loading with Selenium"
        )


        if not self.selenium:

            self.selenium = (
                self.create_driver()
            )



        self.selenium.get(
            self.url
        )



        WebDriverWait(
            self.selenium,
            self.timeout
        ).until(

            lambda d:

            d.execute_script(
                "return document.readyState"
            )
            == "complete"

        )



        return {

            "html":
            self.selenium.page_source,


            "url":
            self.selenium.current_url,


            "title":
            self.selenium.title

        }



    # --------------------------------------------------------
    # Main loader
    # --------------------------------------------------------


    def load_page(self):


        flare = (
            self.flaresolverr()
        )



        if flare:


            logging.info(
                "FlareSolverr successful"
            )


            if flare.get(
                "cookies"
            ):


                self.selenium = (
                    self.create_driver()
                )


                self.add_cookies_to_selenium(
                    flare["cookies"]
                )


                return (
                    self.selenium_load()
                )



            return flare



        return (
            self.selenium_load()
        )
    # --------------------------------------------------------
    # Protection detection
    # --------------------------------------------------------

    def detect_protection(
        self,
        html
    ):

        checks = [

            "cloudflare",

            "checking your browser",

            "challenge-platform",

            "captcha",

            "hcaptcha",

            "recaptcha"

        ]


        found = []


        text = html.lower()


        for item in checks:

            if item in text:

                found.append(
                    item
                )


        return found



    # --------------------------------------------------------
    # Debugging
    # --------------------------------------------------------

    def save_debug(
        self,
        html
    ):

        path = (
            DEBUG_DIR /
            "failed_page.html"
        )


        with open(
            path,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                html
            )


        logging.info(
            "Debug page saved: %s",
            path
        )



    # --------------------------------------------------------
    # Form selection
    # --------------------------------------------------------

    def find_login_form(
        self,
        soup
    ):

        forms = soup.find_all(
            "form"
        )


        if not forms:

            return soup



        best_form = None
        best_score = 0



        for form in forms:


            score = 0


            inputs = form.find_all(
                "input"
            )


            for field in inputs:


                field_type = field.get(
                    "type",
                    ""
                ).lower()


                if field_type == "password":

                    score += 50



                text = " ".join(

                    [

                        field.get(
                            "name",
                            ""
                        ),

                        field.get(
                            "id",
                            ""
                        ),

                        field.get(
                            "placeholder",
                            ""
                        )

                    ]

                ).lower()



                for word in (
                    self.USERNAME_HINTS
                    +
                    self.PASSWORD_HINTS
                ):

                    if word in text:

                        score += 10



            if score > best_score:

                best_score = score

                best_form = form



        return best_form or soup



    # --------------------------------------------------------
    # Field scoring
    # --------------------------------------------------------

    def score_username(
        self,
        field
    ):

        score = 0


        attributes = [

            field.get(
                "id",
                ""
            ),

            field.get(
                "name",
                ""
            ),

            field.get(
                "placeholder",
                ""
            ),

            field.get(
                "aria-label",
                ""
            ),

            field.get(
                "type",
                ""
            )

        ]


        text = (
            " ".join(attributes)
            .lower()
        )


        for hint in self.USERNAME_HINTS:

            if hint in text:

                score += 25



        if field.get(
            "type"
        ) == "email":

            score += 20



        return score



    def score_password(
        self,
        field
    ):

        score = 0



        if field.get(
            "type",
            ""
        ).lower() == "password":

            score += 100



        attributes = [

            field.get(
                "id",
                ""
            ),

            field.get(
                "name",
                ""
            ),

            field.get(
                "placeholder",
                ""
            )

        ]



        text = (
            " ".join(attributes)
            .lower()
        )



        for hint in self.PASSWORD_HINTS:

            if hint in text:

                score += 25



        return score



    def score_submit(
        self,
        element
    ):

        score = 0



        if element.name == "button":

            score += 25



        if element.get(
            "type",
            ""
        ).lower() == "submit":

            score += 50



        text = (

            element.get_text(
                " ",
                strip=True
            )
            +
            " "
            +
            element.get(
                "value",
                ""
            )

        ).lower()



        for hint in self.SUBMIT_HINTS:

            if hint in text:

                score += 25



        return score




    # --------------------------------------------------------
    # Find highest scoring element
    # --------------------------------------------------------

    def best_element(
        self,
        elements,
        scoring
    ):

        ranked = []


        for element in elements:


            score = scoring(
                element
            )


            if score:

                ranked.append(

                    (
                        score,
                        element
                    )

                )



        if not ranked:

            return None, 0



        ranked.sort(
            key=lambda x: x[0],
            reverse=True
        )


        return ranked[0]



    # --------------------------------------------------------
    # Selector generation
    # --------------------------------------------------------

    def xpath(
        self,
        element
    ):


        if element.get(
            "id"
        ):

            return (
                f"//*[@id='{element['id']}']"
            )


        if element.get(
            "name"
        ):

            return (

                f"//{element.name}"
                f"[@name='{element['name']}']"

            )



        attributes = []


        for attr in [
            "type",
            "placeholder",
            "class"
        ]:


            value = element.get(
                attr
            )


            if value:


                if isinstance(
                    value,
                    list
                ):

                    value = (
                        " ".join(value)
                    )


                attributes.append(

                    f"@{attr}='{value}'"

                )



        if attributes:


            return (

                f"//{element.name}"
                f"[{' and '.join(attributes)}]"

            )



        return (
            f"//{element.name}"
        )




    def selector(
        self,
        element
    ):


        if element.get(
            "id"
        ):

            return (
                element["id"],
                "ID"
            )



        if element.get(
            "name"
        ):

            return (
                element["name"],
                "NAME"
            )



        return (

            self.xpath(
                element
            ),

            "XPATH"

        )



    # --------------------------------------------------------
    # Extract configuration
    # --------------------------------------------------------

    def extract(
        self
    ):


        page = (
            self.load_page()
        )


        html = page["html"]



        protection = (
            self.detect_protection(
                html
            )
        )


        if protection:

            logging.warning(

                "Protection detected: %s",

                ", ".join(
                    protection
                )

            )



        soup = BeautifulSoup(
            html,
            "lxml"
        )



        form = (
            self.find_login_form(
                soup
            )
        )



        inputs = form.find_all(
            "input"
        )


        buttons = form.find_all(
            [
                "button",
                "input"
            ]
        )



        username = (
            self.best_element(
                inputs,
                self.score_username
            )
        )


        password = (
            self.best_element(
                inputs,
                self.score_password
            )
        )


        submit = (
            self.best_element(
                buttons,
                self.score_submit
            )
        )



        if not username[1]:

            self.save_debug(
                html
            )

            raise RuntimeError(
                "Username field not found"
            )



        if not password[1]:

            self.save_debug(
                html
            )

            raise RuntimeError(
                "Password field not found"
            )



        if not submit[1]:

            self.save_debug(
                html
            )

            raise RuntimeError(
                "Submit button not found"
            )



        login_box, login_type = (
            self.selector(
                username[1]
            )
        )


        password_box, password_type = (
            self.selector(
                password[1]
            )
        )


        submit_box, submit_type = (
            self.selector(
                submit[1]
            )
        )



        confidence = int(

            (
                username[0]
                +
                password[0]
                +
                submit[0]

            )

            /
            3

        )



        return {


            "url":
            self.url,


            "login_url":
            page["url"],


            "login_title":
            page.get(
                "title",
                ""
            ),



            "login_box":
            login_box,


            "login_box_type":
            login_type,



            "password_box":
            password_box,


            "password_box_type":
            password_type,



            "submit_box":
            submit_box,


            "submit_box_type":
            submit_type,



            "_confidence":
            confidence

        }
# ============================================================
# Configuration file handling
# ============================================================


def load_config(
    filename
):

    path = Path(
        filename
    )


    if not path.exists():

        return {}


    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )


    except Exception as exc:

        logging.error(
            "Unable to read existing config: %s",
            exc
        )

        raise




def save_config(
    filename,
    data
):

    path = Path(
        filename
    )


    #
    # Write safely:
    # - create temporary file
    # - replace original
    #

    temp = tempfile.NamedTemporaryFile(

        mode="w",

        delete=False,

        encoding="utf-8",

        dir=path.parent

    )


    try:

        json.dump(

            data,

            temp,

            indent=4,

            ensure_ascii=False

        )


        temp.close()


        shutil.move(

            temp.name,

            path

        )


    finally:


        if os.path.exists(
            temp.name
        ):

            os.remove(
                temp.name
            )


    logging.info(
        "Saved configuration: %s",
        filename
    )





# ============================================================
# CLI
# ============================================================


def main():

    global FLARESOLVERR_URL
    global FLARESOLVERR_ENABLED



    parser = argparse.ArgumentParser(

        description=(

            "Generate TrackerAutoLogin "
            "tracker_config.json entries"

        )

    )



    parser.add_argument(

        "url",

        help="Tracker login URL"

    )



    parser.add_argument(

        "--name",

        required=True,

        help="Tracker name"

    )



    parser.add_argument(

        "-o",

        "--output",

        default=DEFAULT_CONFIG_FILE,

        help="tracker_config.json location"

    )



    parser.add_argument(

        "--flaresolverr",

        default=FLARESOLVERR_URL,

        help="FlareSolverr URL"

    )



    parser.add_argument(

        "--disable-flaresolverr",

        action="store_true",

        help="Disable FlareSolverr"

    )



    args = parser.parse_args()



    FLARESOLVERR_URL = (
        args.flaresolverr
    )


    if args.disable_flaresolverr:

        FLARESOLVERR_ENABLED = False




    try:


        extractor = TrackerExtractor(

            args.url

        )


        logging.info(
            "Extracting %s",
            args.name
        )


        tracker_data = (
            extractor.extract()
        )



        config = load_config(

            args.output

        )



        #
        # Add/update tracker
        #

        if args.name in config:


            logging.warning(

                "%s already exists. Updating.",

                args.name

            )



        config[args.name] = tracker_data



        save_config(

            args.output,

            config

        )



        print()

        print(
            json.dumps(
                {
                    args.name:
                    tracker_data
                },

                indent=4

            )
        )



    except Exception as exc:


        logging.error(
            "Failed: %s",
            exc
        )


        sys.exit(1)





if __name__ == "__main__":

    main()
