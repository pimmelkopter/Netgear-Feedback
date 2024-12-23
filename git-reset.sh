cp git-reset.sh git-reset.bak
echo "dhcp nicht vergessen!"
git fetch origin
git reset --hard origin/raspberrypi
sudo chmod +x update.sh
sudo chmod +x run.sh
sudo chmod +x setup.sh
mv git-reset.bak git-reset.sh
sudo chmod +x git-reset.sh
./update.sh