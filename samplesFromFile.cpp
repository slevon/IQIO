//
// Copyright 2011-2012,2014 Ettus Research LLC
// Copyright 2018 Ettus Research, a National Instruments Company
//
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <uhd/types/tune_request.hpp>
#include <uhd/usrp/multi_usrp.hpp>
#include <uhd/utils/safe_main.hpp>
#include <uhd/utils/thread.hpp>
#include <boost/format.hpp>
#include <boost/program_options.hpp>
#include <chrono>
#include <complex>
#include <csignal>
#include <fstream>
#include <iostream>
#include <thread>

#include <numeric>

//Udp:
#include <boost/asio.hpp>

namespace po = boost::program_options;

static bool stop_signal_called = false;
void sig_int_handler(int)
{
    stop_signal_called = true;
}

template <typename samp_type>
void send_from_file_udp_only(
    const std::string& file, size_t samps_per_buff)
{
  std::vector<samp_type> buff(samps_per_buff);
  std::ifstream infile(file.c_str(), std::ifstream::binary);
  //IPC file:
  std::ofstream comfile("/dev/shm/samplesFromFile");
  //UDP Packet send
  boost::asio::io_service io_service;
  boost::asio::ip::udp::socket socket(io_service);
  socket.open(boost::asio::ip::udp::v4());
  socket.set_option(boost::asio::socket_base::broadcast(true));
  boost::asio::ip::udp::endpoint endpoint_(boost::asio::ip::address::from_string("0.0.0.0"), 50207);

  // loop until the entire file has been read
  size_t tot_samples_sent = 0;
  while (not infile.eof() and not stop_signal_called) {
    infile.read((char*)&buff.front(), buff.size() * sizeof(samp_type));
    size_t num_tx_samps = size_t(infile.gcount() / sizeof(samp_type));
    //Max
    auto maxelem=max_element(buff.begin(), buff.end(),
                               [](auto a, auto b) { return abs(a) < abs(b); });
    auto nabs=abs(*maxelem);
    //Mean
    static const auto abssum = [] (auto x, auto y) {return x + std::abs(y);};
    double sum = std::accumulate(buff.begin(), buff.end(), 0.0,abssum);
    double mean =  sum / buff.size();

    tot_samples_sent += num_tx_samps;
    comfile << "Samples\t"<< tot_samples_sent  << "\tMax\t" << nabs <<"\tMean\t"<<mean<<std::endl;
    //UDP Send:
    socket.send_to(boost::asio::buffer((char*)&buff.front(), buff.size()), endpoint_ );
  }
    infile.close();
    std::cout << "Total Buffers sent:"<<tot_samples_sent/samps_per_buff << '\n';
}

template <typename samp_type>
void send_from_file(
    uhd::tx_streamer::sptr tx_stream, const std::string& file, size_t samps_per_buff)
{
    uhd::tx_metadata_t md;
    md.start_of_burst = false;
    md.end_of_burst   = false;
    std::vector<samp_type> buff(samps_per_buff);
    std::cout << "Buffersize: "<< buff.size() << '\n';
    std::ifstream infile(file.c_str(), std::ifstream::binary);
    //IPC file:
    std::ofstream comfile("/dev/shm/samplesFromFile");

    //UDP Packet send:
    boost::asio::io_service io_service;
    boost::asio::ip::udp::socket socket(io_service);
    socket.open(boost::asio::ip::udp::v4());
    socket.set_option(boost::asio::socket_base::broadcast(true));
    boost::asio::ip::udp::endpoint endpoint_(boost::asio::ip::address::from_string("0.0.0.0"), 50207);


    // loop until the entire file has been read
    size_t tot_samples_sent = 0;
    while (not md.end_of_burst and not stop_signal_called) {
        infile.read((char*)&buff.front(), buff.size() * sizeof(samp_type));
        size_t num_tx_samps = size_t(infile.gcount() / sizeof(samp_type));
        //Max
        auto maxelem=max_element(buff.begin(), buff.end(),
                                   [](auto a, auto b) { return abs(a) < abs(b); });
        auto nabs=abs(*maxelem);
        //Mean
        static const auto abssum = [] (auto x, auto y) {return x + std::abs(y);};
        double sum = std::accumulate(buff.begin(), buff.end(), 0.0,abssum);
        double mean =  sum / buff.size();

        md.end_of_burst = infile.eof();

        const size_t samples_sent = tx_stream->send(&buff.front(), num_tx_samps, md);
        if (samples_sent != num_tx_samps) {
            UHD_LOG_ERROR("TX-STREAM",
                "The tx_stream timed out sending " << num_tx_samps << " samples ("
                                                   << samples_sent << " sent).");
            return;
        }

        tot_samples_sent += samples_sent;
        comfile << "Samples\t"<< tot_samples_sent  << "\tMax\t" << nabs <<"\tMean\t"<<mean<<std::endl;
        //UDP Send:
        socket.send_to(boost::asio::buffer((char*)&buff.front(), buff.size()), endpoint_ );

    }

    infile.close();
    comfile.close();
}

int UHD_SAFE_MAIN(int argc, char* argv[])
{
    // variables to be set by po
    std::string args, file, type, ant, subdev, ref, wirefmt, channel;
    size_t spb;
    double rate, freq, gain, bw, delay, lo_offset;

    // setup the program options
    po::options_description desc("Allowed options");
    // clang-format off
    desc.add_options()
        ("help", "help message")
        ("args", po::value<std::string>(&args)->default_value(""), "multi uhd device address args")
        ("file", po::value<std::string>(&file)->default_value("usrp_samples.dat"), "name of the file to read binary samples from")
        ("type", po::value<std::string>(&type)->default_value("short"), "sample type: double, float, or short")
        ("spb", po::value<size_t>(&spb)->default_value(10000), "samples per buffer")
        ("rate", po::value<double>(&rate), "rate of outgoing samples")
        ("freq", po::value<double>(&freq), "RF center frequency in Hz")
        ("lo-offset", po::value<double>(&lo_offset)->default_value(0.0),
            "Offset for frontend LO in Hz (optional)")
        ("gain", po::value<double>(&gain), "gain for the RF chain")
        ("ant", po::value<std::string>(&ant), "antenna selection")
        ("subdev", po::value<std::string>(&subdev), "subdevice specification")
        ("bw", po::value<double>(&bw), "analog frontend filter bandwidth in Hz")
        ("ref", po::value<std::string>(&ref)->default_value("internal"), "reference source (internal, external, mimo)")
        ("wirefmt", po::value<std::string>(&wirefmt)->default_value("sc16"), "wire format (sc8 or sc16)")
        ("delay", po::value<double>(&delay)->default_value(0.0), "specify a delay between repeated transmission of file (in seconds)")
        ("channel", po::value<std::string>(&channel)->default_value("0"), "which channel to use")
        ("repeat", "repeatedly transmit file")
        ("udp", "send samples using udp on port 50207")
        ("int-n", "tune USRP with integer-n tuning")
        ("echo-only", "only print the samples to udp port")
    ;
    // clang-format on
    po::variables_map vm;
    po::store(po::parse_command_line(argc, argv, desc), vm);
    po::notify(vm);

    // print the help message
    if (vm.count("help")) {
        std::cout << boost::format("UHD TX samples from file %s") % desc << std::endl;
        return ~0;
    }

    bool repeat = vm.count("repeat") > 0;
    bool echo_only = vm.count("echo-only") > 0;

    if(not echo_only){
    // create a usrp device
    std::cout << std::endl;
    std::cout << boost::format("Creating the usrp device with: %s...") % args
              << std::endl;
    uhd::usrp::multi_usrp::sptr usrp = uhd::usrp::multi_usrp::make(args);

    // Lock mboard clocks
    if (vm.count("ref")) {
        usrp->set_clock_source(ref);
    }

    // always select the subdevice first, the channel mapping affects the other settings
    if (vm.count("subdev"))
        usrp->set_tx_subdev_spec(subdev);

    std::cout << boost::format("Using Device: %s") % usrp->get_pp_string() << std::endl;

    // set the sample rate
    if (not vm.count("rate")) {
        std::cerr << "Please specify the sample rate with --rate" << std::endl;
        return ~0;
    }
    std::cout << boost::format("Setting TX Rate: %f Msps...") % (rate / 1e6) << std::endl;
    usrp->set_tx_rate(rate);
    std::cout << boost::format("Actual TX Rate: %f Msps...") % (usrp->get_tx_rate() / 1e6)
              << std::endl
              << std::endl;

    // set the center frequency
    if (not vm.count("freq")) {
        std::cerr << "Please specify the center frequency with --freq" << std::endl;
        return ~0;
    }
    std::cout << boost::format("Setting TX Freq: %f MHz...") % (freq / 1e6) << std::endl;
    std::cout << boost::format("Setting TX LO Offset: %f MHz...") % (lo_offset / 1e6)
              << std::endl;
    uhd::tune_request_t tune_request;
    tune_request = uhd::tune_request_t(freq, lo_offset);
    if (vm.count("int-n"))
        tune_request.args = uhd::device_addr_t("mode_n=integer");
    usrp->set_tx_freq(tune_request);
    std::cout << boost::format("Actual TX Freq: %f MHz...") % (usrp->get_tx_freq() / 1e6)
              << std::endl
              << std::endl;

    // set the rf gain
    if (vm.count("gain")) {
        std::cout << boost::format("Setting TX Gain: %f dB...") % gain << std::endl;
        usrp->set_tx_gain(gain);
        std::cout << boost::format("Actual TX Gain: %f dB...") % usrp->get_tx_gain()
                  << std::endl
                  << std::endl;
    }

    // set the analog frontend filter bandwidth
    if (vm.count("bw")) {
        std::cout << boost::format("Setting TX Bandwidth: %f MHz...") % (bw / 1e6)
                  << std::endl;
        usrp->set_tx_bandwidth(bw);
        std::cout << boost::format("Actual TX Bandwidth: %f MHz...")
                         % (usrp->get_tx_bandwidth() / 1e6)
                  << std::endl
                  << std::endl;
    }

    // set the antenna
    if (vm.count("ant"))
        usrp->set_tx_antenna(ant);

    // allow for some setup time:
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // Check Ref and LO Lock detect
    std::vector<std::string> sensor_names;
    sensor_names = usrp->get_tx_sensor_names(0);
    if (std::find(sensor_names.begin(), sensor_names.end(), "lo_locked")
        != sensor_names.end()) {
        uhd::sensor_value_t lo_locked = usrp->get_tx_sensor("lo_locked", 0);
        std::cout << boost::format("Checking TX: %s ...") % lo_locked.to_pp_string()
                  << std::endl;
        UHD_ASSERT_THROW(lo_locked.to_bool());
    }
    sensor_names = usrp->get_mboard_sensor_names(0);
    if ((ref == "mimo")
        and (std::find(sensor_names.begin(), sensor_names.end(), "mimo_locked")
             != sensor_names.end())) {
        uhd::sensor_value_t mimo_locked = usrp->get_mboard_sensor("mimo_locked", 0);
        std::cout << boost::format("Checking TX: %s ...") % mimo_locked.to_pp_string()
                  << std::endl;
        UHD_ASSERT_THROW(mimo_locked.to_bool());
    }
    if ((ref == "external")
        and (std::find(sensor_names.begin(), sensor_names.end(), "ref_locked")
             != sensor_names.end())) {
        uhd::sensor_value_t ref_locked = usrp->get_mboard_sensor("ref_locked", 0);
        std::cout << boost::format("Checking TX: %s ...") % ref_locked.to_pp_string()
                  << std::endl;
        UHD_ASSERT_THROW(ref_locked.to_bool());
    }
    // set sigint if user wants to receive
    if (repeat) {
        std::signal(SIGINT, &sig_int_handler);
        std::cout << "Press Ctrl + C to stop streaming..." << std::endl;
    }
    // create a transmit streamer
    std::string cpu_format;
    std::vector<size_t> channel_nums;
    if (type == "double")
        cpu_format = "fc64";
    else if (type == "float")
        cpu_format = "fc32";
    else if (type == "short")
        cpu_format = "sc16";
    uhd::stream_args_t stream_args(cpu_format, wirefmt);
    channel_nums.push_back(boost::lexical_cast<size_t>(channel));
    stream_args.channels             = channel_nums;
    uhd::tx_streamer::sptr tx_stream = usrp->get_tx_stream(stream_args);
    // send from file
    do {
        if (type == "double")
            send_from_file<std::complex<double>>(tx_stream, file, spb);
        else if (type == "float")
            send_from_file<std::complex<float>>(tx_stream, file, spb);
        else if (type == "short")
            send_from_file<std::complex<short>>(tx_stream, file, spb);
        else
            throw std::runtime_error("Unknown type " + type);

        if (repeat and delay > 0.0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(int64_t(delay * 1000)));
        }
    } while (repeat and not stop_signal_called);
  }else{//echo only mode
    std::cout << "echo_only:" << '\n';
    do {
        if (type == "double")
            send_from_file_udp_only<std::complex<double>>( file, spb);
        else if (type == "float")
            send_from_file_udp_only<std::complex<float>>( file, spb);
        else if (type == "short")
            send_from_file_udp_only<std::complex<short>>( file, spb);
        else
            throw std::runtime_error("Unknown type " + type);

        if (repeat and delay > 0.0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(int64_t(delay * 1000)));
        }
    } while (repeat and not stop_signal_called);
  }
    // finished
    std::cout << std::endl << "Done!" << std::endl << std::endl;

    return EXIT_SUCCESS;
}
