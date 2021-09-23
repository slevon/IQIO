//
// Copyright 2010-2011,2014 Ettus Research LLC
// Copyright 2018 Ettus Research, a National Instruments Company
//
// SPDX-License-Identifier: GPL-3.0-or-later
//
//THis tool reads from shared memory file and writes to HDD file


#include <uhd/exception.hpp>
#include <uhd/types/tune_request.hpp>
#include <uhd/usrp/multi_usrp.hpp>
#include <uhd/utils/safe_main.hpp>
#include <uhd/utils/thread.hpp>
#include <boost/format.hpp>
#include <boost/lexical_cast.hpp>
#include <boost/program_options.hpp>
#include <chrono>
#include <complex>
#include <csignal>
#include <fstream>
#include <iostream>
#include <thread>

//File things
#include <string>
#include <iostream>
#include <fstream>
#include <iostream>
#include <filesystem>

///////////////////////////////////////////////////////
//RA new for Compression
#include <boost/iostreams/filtering_streambuf.hpp>
#include <boost/iostreams/copy.hpp>
#include <boost/iostreams/filter/gzip.hpp>
///////////////////////////////////////////////////////

namespace po = boost::program_options;
namespace fs = std::filesystem;

bool copyFromFile(std::string inDir, std::string outDir, bool stats,bool progress,bool compress){
	std::ofstream outfile;
	std::fstream infile;
	fs::path outD=outDir;
    while (true){
		for (const auto& entry : fs::directory_iterator(inDir)) {
			fs::path basename =  entry.path().filename();
			fs::path outPath= outD / basename;
			std::cout << entry.path().string() << "\tto "<< outPath.string()<< std::endl;

			outfile.open(outPath.string().c_str(), std::ofstream::binary);
			infile.open(entry.path().string().c_str(), std::fstream::binary);
			if(!outfile){std::cerr<<"Could not open target"<<std::endl; continue;}
			if(!infile){std::cerr<<"Could not open source"<<std::endl; continue;}
			boost::iostreams::filtering_streambuf<boost::iostreams::output> outbuf;
			if(compress){
				std::cout<<"Compressing"<<std::endl;
				outbuf.push(boost::iostreams::gzip_compressor());
			}
			outbuf.push(outfile);
			//Convert streambuf to ostream
			std::ostream out(&outbuf);
			out << infile.rdbuf();
			outfile.close();
			infile.close();
		}
	std::cout<<"Waiting..."<<std::endl;
	sleep(5);
	}

    return true;
}

int UHD_SAFE_MAIN(int argc, char* argv[])
{
    // variables to be set by po
    std::string inDir, outDir;

    // setup the program options
    po::options_description desc("Allowed options");
    // clang-format off
    desc.add_options()
        ("help", "help message")
        ("in", po::value<std::string>(&inDir)->default_value("/dev/shm/usrp/"), "name of dir to read from")
        ("out", po::value<std::string>(&outDir)->default_value("/home/pi/"), "name of the dir to write to")
        ("progress", "periodically display short-term bandwidth")
        ("stats", "show average bandwidth on exit")
        ("compress", "enable compression")
    ;
    // clang-format on
    po::variables_map vm;
    po::store(po::parse_command_line(argc, argv, desc), vm);
    po::notify(vm);

    // print the help message
    if (vm.count("help")) {
        std::cout << boost::format("UHD RX dump samples to file %s") % desc << std::endl;
        std::cout << std::endl
                  << "Save data to disk "
                     "\n"
                  << std::endl;
        return ~0;
    }

    bool progress             = vm.count("progress") > 0;
    bool stats                  = vm.count("stats") > 0;
    bool compress                  = vm.count("compress") > 0;
 
	copyFromFile(inDir,outDir,stats,progress,compress);

    // finished
    std::cout << std::endl << "Done!" << std::endl << std::endl;

    return EXIT_SUCCESS;
}
