import requests
import base64
import os
#creating GitHubUploadAgent for uploading file to github
class GitHubUploadAgent:
    def __init__(self, token, owner, repo):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"

    def upload_file(self, local_file_path, github_file_path, commit_message):
        # Read file
        with open(local_file_path, "rb") as file:
            content = file.read()

        # Encode file content
        encoded_content = base64.b64encode(content).decode("utf-8")

        url = f"{self.api_url}/{github_file_path}"
        #declaring github token and response data(response outcome format)
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        data = {
            "message": commit_message,
            "content": encoded_content
        }

        response = requests.put(url, headers=headers, json=data)

        if response.status_code in [200, 201]:
            print("✅ File uploaded successfully!")
        else:
            print("❌ Upload failed")
            print(response.json())

agent = GitHubUploadAgent(
    
    owner="Karthik6622",
    repo="PYTHON"
)

agent.upload_file(
    local_file_path="C:\\Users\\karthik.r\\OneDrive - ascendion\\Desktop\\aava_token.txt",
    github_file_path="aava_token.txt",
    commit_message="Add aava token file"
)


#
