# GitHub Integration Guide

## Overview

The system supports cloning and indexing GitHub repositories. This guide explains what's needed to integrate with GitHub.

## ✅ What's Already Implemented

1. **Backend Support**
   - GitHub URL validation
   - Repository cloning using GitPython
   - Branch selection support
   - Automatic repository updates (pull)
   - Database storage of GitHub metadata

2. **Frontend Support**
   - UI for selecting GitHub vs Local repository
   - GitHub URL input field
   - Branch selection input

3. **Database Schema**
   - `github_url` column in `java_repositories` table
   - `github_branch` column (defaults to "main")
   - Metadata fields for tracking repository info

## 📋 Requirements

### 1. Python Dependencies

**Already in requirements.txt:**
```bash
GitPython>=3.1.40
```

**Install it:**
```bash
cd backend
pip install GitPython>=3.1.40
```

### 2. System Requirements

- **Git** must be installed on the system
  ```bash
  # Check if Git is installed
  git --version
  
  # Install Git if needed:
  # macOS: brew install git
  # Ubuntu/Debian: sudo apt-get install git
  # Windows: Download from https://git-scm.com/
  ```

### 3. Network Access

- The server must have internet access to clone from GitHub
- Port 22 (SSH) or 443 (HTTPS) must be accessible
- No firewall blocking GitHub domains

## 🔐 Authentication Options

### Public Repositories

**No authentication needed!** Public repositories can be cloned directly:

```
https://github.com/username/repository
https://github.com/username/repository.git
```

### Private Repositories

For private repositories, you need authentication. Currently, the implementation supports:

#### Option 1: SSH Keys (Recommended for Production)

1. **Generate SSH Key** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

2. **Add SSH Key to GitHub:**
   - Copy public key: `cat ~/.ssh/id_ed25519.pub`
   - Go to GitHub → Settings → SSH and GPG keys → New SSH key
   - Paste the key

3. **Use SSH URL format:**
   ```
   git@github.com:username/repository.git
   ```

4. **Test SSH connection:**
   ```bash
   ssh -T git@github.com
   ```

#### Option 2: Personal Access Token (PAT) - HTTPS

1. **Create a GitHub Personal Access Token:**
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Generate new token with `repo` scope
   - Copy the token

2. **Use HTTPS URL with token:**
   ```
   https://<token>@github.com/username/repository.git
   ```

3. **Or configure Git credentials:**
   ```bash
   git config --global credential.helper store
   # Then use: https://github.com/username/repository.git
   # Enter username and token when prompted
   ```

#### Option 3: GitHub App (Enterprise/Advanced)

For enterprise setups, you can use GitHub Apps with fine-grained permissions.

## 🚀 How to Use

### Via UI (Recommended)

1. **Navigate to Marketplace/Administration**
2. **Click "Add Repository" or "Onboard Repository"**
3. **Select "GitHub Repository" option**
4. **Enter:**
   - Repository Name (e.g., "My Project")
   - GitHub URL (e.g., `https://github.com/username/repo`)
   - Branch (default: `main`)
   - Description (optional)
5. **Click "Register"**
6. **The system will:**
   - Clone the repository to `{JAVA_REPOSITORIES_PATH}/{repository_name}`
   - Register it in the database
   - Ready for indexing

### Via API

```bash
POST /java/repositories
Content-Type: application/json

{
  "name": "My GitHub Repo",
  "github_url": "https://github.com/username/repository",
  "github_branch": "main",
  "description": "My project description"
}
```

## ⚙️ Configuration

### Environment Variables

Add to your `.env` file:

```env
# Path where GitHub repositories will be cloned
JAVA_REPOSITORIES_PATH=./java_repositories

# Optional: GitHub credentials (if using PAT)
# GITHUB_TOKEN=ghp_your_token_here
# GITHUB_USERNAME=your_username
```

### Repository Storage Path

Repositories are cloned to:
```
{JAVA_REPOSITORIES_PATH}/{sanitized_repository_name}/
```

Example:
```
./java_repositories/my_project/
├── src/
├── pom.xml
└── README.md
```

## 🔄 Repository Updates

The system automatically updates repositories when you re-register:

1. If repository already exists locally, it runs `git pull`
2. Only changed files are re-indexed (incremental indexing)

## 🛠️ Troubleshooting

### Error: "GitPython is not installed"

```bash
pip install GitPython>=3.1.40
```

### Error: "Failed to clone repository"

**Check:**
1. Repository URL is correct
2. Repository is accessible (public or you have access)
3. Git is installed: `git --version`
4. Network connectivity to GitHub
5. For private repos: SSH keys or PAT configured

### Error: "Permission denied (publickey)"

**For SSH URLs:**
- Ensure SSH key is added to GitHub
- Test: `ssh -T git@github.com`
- Use HTTPS URL instead if SSH isn't configured

**For HTTPS URLs:**
- Use Personal Access Token in URL: `https://<token>@github.com/...`
- Or configure Git credentials globally

### Error: "Repository not found"

- Check repository URL is correct
- For private repos: ensure you have access
- Verify repository exists on GitHub

### Large Repository Timeout

For very large repositories:
- Clone manually first, then use local path
- Or increase timeout in GitPython calls
- Consider using shallow clone (future enhancement)

## 🔒 Security Considerations

1. **Private Repositories:**
   - Store SSH keys securely
   - Use environment variables for tokens (never commit to code)
   - Rotate tokens regularly

2. **Repository Access:**
   - Only clone repositories you have permission to access
   - Review repository contents before indexing
   - Be cautious with repositories containing sensitive data

3. **Storage:**
   - Repository data is stored locally on the server
   - Ensure proper file permissions
   - Consider encryption for sensitive repositories

## 📝 Supported URL Formats

✅ **HTTPS:**
```
https://github.com/username/repository
https://github.com/username/repository.git
```

✅ **SSH:**
```
git@github.com:username/repository.git
```

✅ **With Token (HTTPS):**
```
https://<token>@github.com/username/repository.git
```

❌ **Not Supported:**
- GitHub Enterprise Server (custom domains) - needs additional configuration
- GitLab, Bitbucket, etc. - only GitHub.com is supported

## 🎯 Next Steps

1. **Install GitPython:** `pip install GitPython>=3.1.40`
2. **Install Git:** Ensure Git is installed on your system
3. **Test with Public Repo:** Try cloning a public repository first
4. **Configure Auth (if needed):** Set up SSH keys or PAT for private repos
5. **Start Using:** Register repositories via UI or API

## 🔮 Future Enhancements

Potential improvements:
- [ ] Support for GitHub Enterprise Server
- [ ] Support for other Git hosts (GitLab, Bitbucket)
- [ ] Automatic token management
- [ ] Shallow clone option for large repos
- [ ] Webhook integration for auto-updates
- [ ] Branch switching without re-cloning
- [ ] Submodule support

## 📚 Additional Resources

- [GitPython Documentation](https://gitpython.readthedocs.io/)
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [GitHub SSH Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)

