---
description: Generate a commit message based on staged changes.
---

1. Check the current status and staged changes:
// turbo
   ```bash
   git status
   ```

2. View the actual modifications that will be committed:
// turbo
   ```bash
   git diff --staged
   ```

3. Generate a concise, clear commit message in **English** based on the staged changes.
4. Follow these rules for the commit message:
   - Use the imperative mood in the subject line (e.g., "Add feature", "Fix bug", "Update config").
   - Keep the subject line under 50 characters.
   - If there are multiple logical changes, add a completely blank line followed by a bulleted list in the body explaining the details of the changes.
5. Present the proposed commit message to the user for review. Do not run `git commit` automatically unless explicitly instructed by the user.
