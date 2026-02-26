import requests
from bs4 import BeautifulSoup


class ScraperError(Exception):
    pass


def format_url(url):
    if url.startswith('http://'):
        url = url.replace('http', 'https')
    elif url.startswith('www.'):
        url = url.replace('www.', 'https://')
    elif url.startswith('https://') or url.startswith('https://www.'):
        pass
    else:
        raise ScraperError(
            "Enter the repository URL in the format: "
            "https://github.com/username/repository_name"
        )
    return url


def verify_url(page_data):
    data = str(page_data)
    if "Popular repositories" in data:
        return False
    elif "Page not found" in data:
        return False
    return True


def get_repo_title(html):
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text()
    start = title.find('/')
    stop = title.find(':')
    return title[start + 1: stop]


def get_stargazer_usernames(repo_url):
    import time
    usernames = []
    page = 1
    empty_streak = 0

    while True:
        url = repo_url + "/stargazers?page={}".format(page)
        stargazer_html = requests.get(url, timeout=15).text
        soup = BeautifulSoup(stargazer_html, "lxml")

        found = []
        truncate_spans = soup.findAll("span", {"class": "Truncate-text"})
        for span in truncate_spans:
            a_tag = span.find("a", {"data-hovercard-type": "user"})
            if a_tag:
                href = a_tag.get("href")
                if href:
                    found.append(href.lstrip("/"))

        if found:
            usernames.extend(found)
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= 3:
                break

        page += 1
        time.sleep(1.0)

    return usernames


def get_latest_commit_email(repo_name, username):
    email = ""
    commit_data = requests.get(
        "https://github.com/{}/{}/commits?author={}".format(
            username, repo_name, username
        )
    ).text
    soup = BeautifulSoup(commit_data, "lxml")
    a_tags = soup.findAll("a")
    for a_tag in a_tags:
        url = a_tag.get("href")
        if url and url.startswith("/{}/{}/commit/".format(username, repo_name)):
            label = str(a_tag.get("aria-label"))
            if "Merge" not in label and label != "None":
                patch_data = requests.get(
                    "https://github.com{}.patch".format(url)
                ).text
                try:
                    start = patch_data.index("<")
                    stop = patch_data.index(">")
                    email = patch_data[start + 1: stop]
                except ValueError:
                    return "Not enough information."
                break
    return email if email else "Not enough information."


def get_user_source_repos(username):
    repo_data = requests.get(
        "https://github.com/{}?tab=repositories&type=source".format(username)
    ).text
    repo_soup = BeautifulSoup(repo_data, "lxml")
    a_tags = repo_soup.findAll("a")
    repos = []
    for a_tag in a_tags:
        if a_tag.get("itemprop") == "name codeRepository":
            repos.append(a_tag.get_text().strip())
    return repos


def get_user_email(username):
    repos = get_user_source_repos(username)
    if len(repos) > 0:
        return get_latest_commit_email(repos[0], username)
    return "Not enough information."


def get_user_profile(username):
    profile = {
        "username": username,
        "repositories": 0,
        "stars": "0",
        "followers": "0",
        "following": "0",
        "email": "Not enough information.",
    }

    user_html = requests.get("https://github.com/" + username).text
    soup = BeautifulSoup(user_html, "lxml")

    repos = get_user_source_repos(username)
    profile["repositories"] = len(repos)

    if len(repos) > 0:
        profile["email"] = get_latest_commit_email(repos[0], username)

    items = soup.findAll("a", {"class": "no-underline"})
    for item in items[1:]:
        href = item.get("href")
        if not href:
            continue
        if href.endswith("stars"):
            spans = item.findAll("span")
            if spans:
                profile["stars"] = spans[0].get_text().strip()
        elif href.endswith("followers"):
            spans = item.findAll("span")
            if spans:
                profile["followers"] = spans[0].get_text().strip()
        elif href.endswith("following"):
            spans = item.findAll("span")
            if spans:
                profile["following"] = spans[0].get_text().strip()

    return profile


def scrape_full(repo_url):
    url = format_url(repo_url)
    try:
        html = requests.get(url, timeout=8).text
    except requests.exceptions.RequestException:
        raise ScraperError("Failed to fetch repository page")

    if not verify_url(html):
        raise ScraperError("Invalid repository URL or repository not found")

    repo_name = get_repo_title(html)
    usernames = get_stargazer_usernames(url)
    stargazers = []
    for username in usernames:
        profile = get_user_profile(username)
        stargazers.append(profile)

    return {
        "repo_name": repo_name,
        "stargazer_count": len(stargazers),
        "stargazers": stargazers,
    }


def scrape_emails(repo_url):
    url = format_url(repo_url)
    try:
        html = requests.get(url, timeout=8).text
    except requests.exceptions.RequestException:
        raise ScraperError("Failed to fetch repository page")

    if not verify_url(html):
        raise ScraperError("Invalid repository URL or repository not found")

    repo_name = get_repo_title(html)
    usernames = get_stargazer_usernames(url)
    stargazers = []
    for username in usernames:
        email = get_user_email(username)
        stargazers.append({"username": username, "email": email})

    return {
        "repo_name": repo_name,
        "stargazer_count": len(stargazers),
        "stargazers": stargazers,
    }
