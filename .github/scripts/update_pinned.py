import requests
import re

def main():
    username = "ReZaiden"
    url = f"https://api.github.com/users/{username}/repos?sort=stars&direction=desc&per_page=12"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ReZaiden-Profile-Update"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return
    
    repos = response.json()
    
    pinned_section = "### 📌 Pinned Projects\n\n<div align=\"center\">\n\n"
    count = 0
    
    for repo in repos:
        if repo.get('fork') or repo.get('archived') or repo.get('private'):
            continue
        if count >= 6:
            break
            
        name = repo['name']
        html_url = repo['html_url']
        description = repo.get('description') or "No description provided."
        stars = repo.get('stargazers_count', 0)
        language = repo.get('language') or "Python"
        
        card = f"""<a href="{html_url}">
  <img align="center" src="https://github-readme-stats.vercel.app/api/pin/?username={username}&repo={name}&theme=dark&hide_border=true&border_color=00FFAA" alt="{name}"/>
</a>"""
        
        pinned_section += card + "\n\n"
        count += 1
    
    pinned_section += "</div>\n\n"
    
    # Read README
    with open('README.md', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace pinned section
    if '### 📌 Pinned Projects' in content:
        new_content = re.sub(
            r'### 📌 Pinned Projects[\s\S]*?(?=### 📊 Activity|\Z)',
            pinned_section,
            content,
            flags=re.MULTILINE
        )
    else:
        new_content = content.rstrip() + "\n\n" + pinned_section
    
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ Updated {count} beautiful pinned project cards!")

if __name__ == "__main__":
    main()
