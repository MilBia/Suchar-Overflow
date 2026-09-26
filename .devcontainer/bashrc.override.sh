
#
# .bashrc.override.sh
#

# persistent bash history
HISTFILE=~/.bash_history
PROMPT_COMMAND="history -a; $PROMPT_COMMAND"

# DATABASE_URL comes from the image's /etc/bash.bashrc (compose/local/django/bashrc.sh,
# #404), which runs before ~/.bashrc and never leaks the entrypoint's shell options.

# start ssh-agent
# https://code.visualstudio.com/docs/remote/troubleshooting
eval "$(ssh-agent -s)"
