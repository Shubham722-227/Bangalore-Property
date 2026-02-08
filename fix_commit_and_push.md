# Remove co-author and push

The last commit may include a "Co-authored-by" line added by the editor. To remove it and push with only your author line:

**Run these commands in a normal terminal (PowerShell or Git Bash) outside Cursor:**

```powershell
cd c:\Users\Work\Project\Banglprop

# Rewrite the last commit message (no co-author)
git commit --amend -m "Initial commit: Bangalore property scraper and viewer"

# Push to GitHub (you may be prompted to sign in)
git push -u origin main
```

After the first push, use `git push` for future updates.
