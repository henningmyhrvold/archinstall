#!/bin/bash
sudo pacman -S --needed sbctl

sudo sbctl create-keys
sudo sbctl enroll-keys -m
# chattr -i <file>
sudo sbctl verify | sed 's/✗ /sudo sbctl sign -s /e'
sudo sbctl status
