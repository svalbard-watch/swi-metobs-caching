#!/bin/bash
# Refresh the station configuration before each run. Started by run-cron (swi-cron-base) as
# SWI_CRON_PRE_COMMAND, so a failure here aborts the run; a failed `git pull` is tolerated
# because the configuration already on disk is still usable.

REPO_URL="https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-station-configuration.git"
FOLDER_NAME="config"
OTHER_CONFIG="/swi/data/__swi-config__"

INITIAL_DIR=$(pwd)

if [ -d "$FOLDER_NAME" ]; then
    echo "Folder '$FOLDER_NAME' exists. Pulling the latest changes..."
    cd "$FOLDER_NAME" || exit 1
    git pull origin main || echo "git pull failed; continuing with the configuration on disk"
    cd "$INITIAL_DIR" || exit 1
else
    echo "Folder '$FOLDER_NAME' does not exist. Cloning the repository..."
    git clone "$REPO_URL" "$FOLDER_NAME" || exit 1
fi

if [ ! -d "$OTHER_CONFIG" ]; then
    echo "Creating directory '$OTHER_CONFIG'..."
    mkdir -p "$OTHER_CONFIG" || exit 1
fi

echo "Copying files from '$FOLDER_NAME' to '$OTHER_CONFIG' (overwriting existing files)..."
cp -rf "$FOLDER_NAME"/* "$OTHER_CONFIG/" || exit 1
