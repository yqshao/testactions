import os
import git
import requests
import json
import difflib


def get_first_commit_date(repo, file_path):
    commits = list(repo.iter_commits(paths=file_path))
    return commits[-1].committed_date


def sort_files_by_added_date(repo, file_paths):
    files_with_dates = [(get_first_commit_date(repo, file_path), file_path) for file_path in file_paths]
    sorted_files = sorted(files_with_dates)
    return [file for file, date in sorted_files]


def similar_easyconfigs(repo, new_file):
    d = os.path.dirname(new_file)
    possible_neighbours = [path for path in os.listdir(d) if path.endswith('.eb')]
    return sort_by_added_date(repo, possible_neighbours)[:3] # top 3


def diff(old, new):
    with open(old, 'r') as old_file, open(new, 'r') as new_file:
        return difflib.unified_diff(
            old_file,
            new_file,
            fromfile=old,
            tofile=new)
        

GITHUB_API_URL = 'https://api.github.com'
event_path = os.getenv("GITHUB_EVENT_PATH")
token = os.getenv("GH_TOKEN")
repo = os.getenv("GITHUB_REPOSITORY")
base_branch_name = os.getenv("GITHUB_BASE_REF")
pr_branch_name = os.getenv("GITHUB_HEAD_REF")

with open(event_path) as f:
    data = json.load(f)

pr_number = data['pull_request']['number']

print("PR number:", pr_number)
print("Repo:", repo)
print("Base branch name:", base_branch_name)
print("PR branch name:", pr_branch_name)

gitrepo = git.Repo(".")
branches = {x.name: x for x in gitrepo.remote().refs}
base_branch = branches['origin/' + base_branch_name]
pr_branch = branches['origin/' + pr_branch_name]

pr_diff = base_branch.commit.diff(pr_branch.commit)
new_ecs = [item.a_path for item in pr_diff if item.change_type == 'A' and item.a_path.endswith('.eb')]
changed_ecs = [item.a_path for item in pr_diff if item.change_type != 'A' and item.a_path.endswith('.eb')]

print("Changed ECs:", changed_ecs)
print("Newly added ECs:", new_ecs)

new_software = False
updated_software = False
comment = ''
for new_file in new_ecs:
    neighbours = similar_easyconfigs(repo, new_file)
    if len(neighbours) == 0:
        new_software = True
    else:
        updated_software = True
    if neighbour:
        comment += '#### Updated software `{new_file}`\n\n'

        for neighbour in neighbours:
            comment += '<details>\n'
            comment += '<summary>Diff against <code>{new_file}</code></summary>\n\n'
            comment += '[neighbour](https://github.com/{repo}/blob/{base_branch_name}/{neighbour})\n\n'
            comment += '```diff\n'
            comment += diff(neighbour, new_file)
            comment += '```\n</details>\n'

# Adjust labeling
current_labels = [label['name'] for label in data['pull_request']['labels']]

labels_add = []
labels_del = []
for condition, label in [(changed_ecs, 'change'), (new_software, 'new'), (updated_software, 'update')]:
    if condition and label not in current_labels:
       labels_add.append(label)
    elif not condition and label in current_labels:
       labels_del.append(label)

url = f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/labels"

headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": f"2022-11-28",
}

if labels_add:
    print(f"Setting labels: {labels_add} at {url}")
    response = requests.post(url, headers=headers, json={"labels": labels_add})
    if response.status_code == 200:
        print(f"Labels {labels_add} added successfully.")
    else:
        print(f"Failed to add labels: {response.status_code}, {response.text}")

for label in labels_del:
    print(f"Removing label: {label} at {url}")
    response = requests.delete(f'{url}/{label}', headers=headers)
    if response.status_code == 200:
        print(f"Label {label} removed successfully.")
    else:
        print(f"Failed to delete label: {response.status_code}, {response.text}")

# Write comment with diff
if updated_software:
    # Search for comment by bot to potentially replace
    url = f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments"
    response = requests.get(url, headers=headers)
    for comment in response.json():
        if comment["user"]["login"] == "github-actions[bot]":  # Bot username in GitHub Actions
            comment_id = comment["id"]

    if comment_id:
        # Update existing comment
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/comments/{comment_id}"
        response = requests.patch(url, headers=headers, json={"body": comment})
        if response.status_code == 200:
            print("Comment updated successfully.")
        else:
            print(f"Failed to update comment: {response.status_code}, {response.text}")
    else:
        # Post a new comment
        url = f"{GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments"
        response = requests.post(url, headers=headers, json={"body": comment})
        if response.status_code == 201:
            print("Comment posted successfully.")
        else:
            print(f"Failed to post comment: {response.status_code}, {response.text}")


