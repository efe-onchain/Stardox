import requests
from bs4 import BeautifulSoup


class ScraperError(Exception):
    pass


# Session configuration
SESSION_KEY = "3TNA6kHk3lknT219MNy2TfAGCiGzwPCb-RvVRROahOMsasD3"
MIN_REPOSITORIES = 20


def get_session():
    """Create a requests session with authentication."""
    session = requests.Session()
    session.cookies.set("user_session", SESSION_KEY, domain="github.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    return session


_session = None


def get_authenticated_session():
    global _session
    if _session is None:
        _session = get_session()
    return _session


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
    session = get_authenticated_session()
    commit_data = session.get(
        "https://github.com/{}/{}/commits?author={}".format(
            username, repo_name, username
        ),
        timeout=15
    ).text
    soup = BeautifulSoup(commit_data, "lxml")
    a_tags = soup.findAll("a")
    for a_tag in a_tags:
        url = a_tag.get("href")
        if url and url.startswith("/{}/{}/commit/".format(username, repo_name)):
            label = str(a_tag.get("aria-label"))
            if "Merge" not in label and label != "None":
                patch_data = session.get(
                    "https://github.com{}.patch".format(url),
                    timeout=15
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
    session = get_authenticated_session()
    repo_data = session.get(
        "https://github.com/{}?tab=repositories&type=source".format(username),
        timeout=15
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
        "company": None,
        "position": None,
        "linkedin": None,
        "email": "Not enough information.",
    }

    session = get_authenticated_session()
    user_html = session.get("https://github.com/" + username, timeout=15).text
    soup = BeautifulSoup(user_html, "lxml")

    repos = get_user_source_repos(username)
    profile["repositories"] = len(repos)

    if len(repos) > 0:
        profile["email"] = get_latest_commit_email(repos[0], username)

    # Extract company/organization
    org_element = soup.find("span", {"class": "p-org"})
    if org_element:
        profile["company"] = org_element.get_text().strip()

    # Also check for organization in the list items
    org_li = soup.find("li", {"itemprop": "worksFor"})
    if org_li:
        org_text = org_li.get_text().strip()
        if org_text and not profile["company"]:
            profile["company"] = org_text

    # Extract bio which often contains position/title
    bio_element = soup.find("div", {"class": "p-note"})
    if bio_element:
        bio_text = bio_element.get_text().strip()
        profile["position"] = bio_text

    # Also check user-profile-bio
    bio_div = soup.find("div", {"data-bio-text": True})
    if bio_div:
        bio_text = bio_div.get("data-bio-text", "").strip()
        if bio_text:
            profile["position"] = bio_text

    # Extract LinkedIn from social links
    social_links = soup.findAll("a", {"rel": "nofollow me"})
    for link in social_links:
        href = link.get("href", "")
        if "linkedin.com" in href.lower():
            profile["linkedin"] = href
            break

    # Also check all external links on profile
    if not profile["linkedin"]:
        all_links = soup.findAll("a", href=True)
        for link in all_links:
            href = link.get("href", "")
            if "linkedin.com/in/" in href.lower():
                profile["linkedin"] = href
                break

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


def profile_qualifies(profile):
    """Check if profile meets the required criteria."""
    # Must have >20 repositories
    if profile.get("repositories", 0) <= MIN_REPOSITORIES:
        return False

    # Must have company OR position listed
    has_company = profile.get("company") and profile["company"].strip()
    has_position = profile.get("position") and profile["position"].strip()

    if not (has_company or has_position):
        return False

    return True


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
