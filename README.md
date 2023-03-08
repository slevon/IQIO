# IQIO

Building UHD Applications using CMake
=====================================

This directory contains a tiny example of a UHD-based application.
Unlike the other examples, it is completely independent of the UHD
source tree and can be compiled from any path as long as UHD is
currently installed on the current machine.

To try it out, run these commands:
$ mkdir build/ # Creates a new build directory
$ cd build/
$ cmake ..
$ make


## Run Save
sudo ./samplesToFile --freq 1030e6 --rate 12e6 --gain 76 --bw 22e6 --duration 1200  --progress --stat


## Run Playback
sudo ./samplesFromFile --file usrp_samples.dat --freq 1030e6 --rate 12e6 --gain 76 --bw 22e6




This will find the UHD libraries, and link and compile the example
program. Include header directories and library names are automatically
gathered.

See the CMakeLists.txt file to figure out how to set up a build system.



## Adding Comprepssion
https://techoverflow.net/2020/01/13/how-to-gzip-compress-on-the-fly-in-c-using-boostiostreams/
https://www.boost.org/doc/libs/1_75_0/libs/iostreams/doc/classes/zlib.html

##  Power Callibarions:
https://files.ettus.com/manual/page_power.html
