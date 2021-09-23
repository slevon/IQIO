# IQIO


#Build

cd build
cmake ../
make


#Run Save
sudo ./samplesToFile --freq 1030e6 --rate 12e6 --gain 76 --bw 22e6 --duration 1200  --progress --stat


#Run Playback
sudo ./samplesFromFile --file usrp_samples.dat --freq 1030e6 --rate 12e6 --gain 76 --bw 22e6
