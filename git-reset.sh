git stash push -- git-reset.sh
echo "dhcp nicht vergessen!"
git reset --hard origin/raspberrypi
#git pull
sudo chmod +x update.sh
sudo chmod +x run.sh
sudo chmod +x setup.sh
git stash apply
sudo chmod +x git-reset.sh
./update.sh