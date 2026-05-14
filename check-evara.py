#!/usr/bin/python

import datetime
import logging
import os
import re
import requests
import subprocess
import sys
import time

from bs4 import BeautifulSoup
from pprint import pprint
from urllib.parse import urlparse, parse_qs


PURPLE = '\033[0;31m'
BLUE = '\033[0;36m'
GREEN = '\033[0;32m'
YELLOW = '\x1b[38;2;228;208;27;m'
BOLD = '\033[1m'
ENDC = '\033[0m'

logging.basicConfig(
    filename='/tmp/CheckEvara.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

MOODLE_URL = "https://moodle.epita.fr"

cookies = None
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

session = requests.Session()

DATA_PATH = os.path.expanduser("~/.local/share/check-evara/")
IMAGE_PATH = DATA_PATH + "logo.png"
IMAGE_URL = "https://media.tenor.com/I72UDkaxRyIAAAAM/67-bunny.gif"

def get_courses(html_dashboard):
    courses = []

    for line in html_dashboard.split("\n"):
        if not "https://moodle.epita.fr/course/view.php?id=" in line:
            continue


        soup = BeautifulSoup(line, 'html.parser')

        link = soup.find('a')
            
        if link:
            # get cours name
            name = link.get('title')

            if name is None:
                continue
                
            # get course link
            href = link.get('href')

            query = urlparse(href).query
            params = parse_qs(query)
            course_id = params.get('id', [None])[0]
            
            courses.append({"name": name, "course_id": course_id})

    return courses

def get_check_presence_from_course(course_id):
    url = f"https://moodle.epita.fr/course/view.php?id={course_id}"
    
    try:
        response = session.get(url, cookies=cookies, headers=headers)
        response.raise_for_status()  # check for errors
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        page_title = soup.find('div', class_='page-header-headings').text.strip()
        
        links = []
        for link in soup.find_all('a', class_='aalink'):
            if "https://moodle.epita.fr/mod/attendance" in link["href"]:
                return link
            
        return None
        
    except Exception as e:
        print( f"Error when trying to get check_presence link from course {course_id} : {e}")
        return None

def get_check_presence_times(course_id):
    full_link = get_check_presence_from_course(course_id)

    if full_link is None:
        return []

    link = full_link['href']

    try:
        response = session.get(link, cookies=cookies, headers=headers)
        response.raise_for_status()  # check for errors
        
        soup = BeautifulSoup(response.text, 'html.parser')

        dates = []

        for date in soup.find_all('td', class_='datecol'):
            date_txt = date.getText()
            date_txt = re.sub(r'\(.*\)', '', date_txt).replace('  ', ' ')
            
            # use to split start time and end time
            # d.m.y (day.) H:M - h:M  =>  [ 'd.m.y H:M ', '' H:M' ]
            date_parts = date_txt.split('-')

            # parse dates and times
            format_str = "%d.%m.%y %H:%M "
            date_start = datetime.datetime.strptime(date_parts[0], format_str)
            format_str = " %H:%M"
            time_end = datetime.datetime.strptime(date_parts[1], format_str)

            # time end is compute for 01/01/1900
            day_delta = date_start.date() - time_end.date()
            time_delta = time_end - date_start + day_delta

            dates.append({ "start": date_start, "duration": time_delta})

        return dates
        
    except Exception as e:
        print(f"Error when trying to get check_presence times : {e}")
        return None


def get_moodle_dashboard():
    # first entry point to get moodle pages
    # So we check that the connection works
    try:
        response = requests.get(f"{MOODLE_URL}/my/", cookies=cookies, headers=headers)
        
        # check if it work
        response.raise_for_status()
        
        # parse content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # searching user menu to check if it work
        user_menu = soup.find('span', class_='userbutton')
        
        if user_menu:
            print(f"Connect as : {user_menu.text.strip()}")
            print("-" * 50)

            return get_courses(response.text)
        else:
            print(f"{PURPLE}{BOLD}Cant find user, check your cookie{ENDC}")
            
    except requests.exceptions.HTTPError as err:
        print(f"{PURPLE}{BOLD}HTTP error: {ENDC}{err}")
    except Exception as e:
        print(f"{PURPLE}{BOLD}Error: {ENDC}{e}")


def check_image():
    if os.path.isfile(IMAGE_PATH):
        return

    try:
        os.makedirs(DATA_PATH)
    except FileExistsError:
        None

    args = ["ls", DATA_PATH]
    subprocess.run(args)
    args = ["wget", IMAGE_URL, f"--output-document={IMAGE_PATH}"]
    subprocess.run(args)


def notification_daemon(times):
    check_image()

    logging.info("Notification daemon launched")
    args = ['notify-send', 'CheckEvara', 'Successfully launched CheckEvara notification daemon', '-a', 'CheckEvara']
    subprocess.run(args)

    while len(times) > 0:
        check = times.pop(0)

        logging.info(f"New Check Presence: {check}")

        # wait until we need to send notif
        wait_time = check['start'] - datetime.datetime.now()
        logging.debug(f"Waiting for: {wait_time.total_seconds()}")
        time.sleep(wait_time.total_seconds())

        logging.info("Running notify-send")

        notif_time = check['duration'].total_seconds() * 1000
        args = ['notify-send', 'CheckEvara', 'There is a Check Presence', '--urgency=critical', '--app-name=CheckEvara', f"--expire-time={str(int(notif_time))}", f"--icon={IMAGE_PATH}"]

        check_image()

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with process.stdout:
            for line in iter(process.stdout.readline, b''): # b'\n'-separated lines
                logging.info('got line from subprocess: %r', line)
        exitcode = process.wait()

        if exitcode != 0:
            logging.error(f"It seem that notify-send failed with args: {args}")


def create_daemon(times):
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            return 

    except OSError as e:
        print(f"Fork error #1: {e}")
        sys.exit(1)

    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        print(f"Fork error #2: {e}")
        sys.exit(1)

    # Daemon has started
    # Redirecting outputs to logs
    sys.stdout = open('/tmp/checkevara_daemon.log', 'a')
    sys.stderr = open('/tmp/checkevara_error.log', 'a')
    
    try:
        notification_daemon(times)
    except Exception as e:
        logging.error(f"Python error: {e}")
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    MOODLE_SESSION_COOKIE = input(BOLD + "Enter your Moodle cookie: " + ENDC).strip()
    cookies = {
        'MoodleSession': MOODLE_SESSION_COOKIE
    }

    courses = get_moodle_dashboard()
    if courses is None:
        exit(1)

    for i in range(len(courses)):
        num = str(len(courses) - i).rjust(4)
        print(f"{GREEN}{num}{YELLOW}  {courses[i]['name']}{ENDC}")
    print()

    idx = -1
    try:
        idx = int(input(BOLD + "Which class to check Check Presence: " + ENDC))
    except:
        print(FAIL + "Invalid class number" + ENDC)
        exit(1)

    if idx < 1 or idx > len(courses):
        print(FAIL + "Invalid class number" + ENDC)
        exit(1)

    course = courses[len(courses) - idx]
    print(f"Search check presence page for {PURPLE}{BOLD}`{course['name']}`{ENDC} with id {PURPLE}{BOLD}`{course['course_id']}`{ENDC}")

    times = get_check_presence_times(course['course_id'])

    # TEST
    times.append({ "start": datetime.datetime.now() + datetime.timedelta(minutes=1), "duration": datetime.timedelta(seconds=30) })
    times.append({ "start": datetime.datetime.now() + datetime.timedelta(seconds=15), "duration": datetime.timedelta(seconds=30) })

    # keep only future check presence
    now = datetime.datetime.now()
    times = [ t for t in times if t['start'] > now ]

    # sort in order of check presence
    times.sort(key=lambda t: t['start'])

    print()
    for t in times:
        print(f"Found check presence at {PURPLE}{BOLD}`{t['start']}`{ENDC}")

    if len(times) == 0:
        print(f"No Check Presence found")
        exit(0)

    # notification_daemon(times) # to debug
    create_daemon(times)
