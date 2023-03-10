//
// Copyright 2010-2011,2014 Ettus Research LLC
// Copyright 2018 Ettus Research, a National Instruments Company
//
// SPDX-License-Identifier: GPL-3.0-or-later
//
#include <stdlib.h>
#include <limits>
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
//Thread
#include <utility>
#include <thread>
#include <queue>
///////////////////////////////////////////////////////
//RA new for Compression
#include <boost/iostreams/filtering_streambuf.hpp>
#include <boost/iostreams/copy.hpp>
#include <boost/iostreams/filter/gzip.hpp>
///////////////////////////////////////////////////////

////////////
//For IPC file
#include <boost/iostreams/tee.hpp>
#include <boost/iostreams/stream.hpp>
#include <fstream>
#include <iostream>

using std::ostream;
using std::ofstream;
using std::cout;

namespace bio = boost::iostreams;
using bio::tee_device;
using bio::stream;


//Use multiple Threads, one for consuming, and one for fiel writing

unsigned int  clipping_occured =0;
unsigned int  overflow_occured =0;
double  peak=0;
template<typename Data>
class concurrent_queue
{
private:
    std::queue<Data> the_queue;
    mutable boost::mutex the_mutex;
    boost::condition_variable the_condition_variable;
public:
    void push(Data const& data)
    {
        boost::mutex::scoped_lock lock(the_mutex);
        the_queue.push(data);
        lock.unlock();
        the_condition_variable.notify_one();
    }

    bool empty() const
    {
        boost::mutex::scoped_lock lock(the_mutex);
        return the_queue.empty();
    }

    bool try_pop(Data& popped_value)
    {
        boost::mutex::scoped_lock lock(the_mutex);
        if(the_queue.empty())
        {
            return false;
        }

        popped_value=the_queue.front();
        the_queue.pop();
        return true;
    }

    void wait_and_pop(Data& popped_value)
    {
        boost::mutex::scoped_lock lock(the_mutex);
        while(the_queue.empty())
        {
            the_condition_variable.wait(lock);
        }

        popped_value=the_queue.front();
        the_queue.pop();
    }

    unsigned int size()
    {
        boost::mutex::scoped_lock lock(the_mutex);
        return the_queue.size();
    }

};


namespace po = boost::program_options;
using namespace std;

static bool stop_signal_called = false;
void sig_int_handler(int)
{
    stop_signal_called = true;
}
///////////////////////////////////////////////////////////////////////////
template <typename samp_type>
void writeToFile(std::ostream &out,
	concurrent_queue<long>& queue_size,
	concurrent_queue<std::vector<samp_type> >& queue_data){

    //////////////////////////
  	//Write To File
  	/////////////////////////


  	long size;
  	std::vector<samp_type> data;
  	while (!(stop_signal_called) || (queue_size.size()>0) ){
  		if(!queue_size.try_pop(size)
        || !queue_data.try_pop(data)){
          sleep(0.5);
        }else{
            //check for clipping:
            // C++14
            auto maxelem = max_element(data.begin(), data.end(),
                                       [](auto a, auto b) { return abs(a) < abs(b); });
            double nabs=abs(*maxelem);
            if(nabs > 0.98 and nabs < 1){ //the float case
                clipping_occured++;
            }else if(nabs > (32767 * 0.98) ){ //the "short case"
                clipping_occured++;
            }
            if (nabs > peak){
              peak = nabs;
            }
            out.write((const char*)&data.front(), size);
        }
  	}
    std::cout<<"Finishing Thread"<<std::endl;
	}
template <typename samp_type>
void recv_to_file(uhd::usrp::multi_usrp::sptr usrp,
    const std::string& cpu_format,
    const std::string& wire_format,
    const size_t& channel,
    std::string& file,  //RA Const removed
    size_t samps_per_buff,
    unsigned long long num_requested_samples,
    double time_requested       = 0.0,
    bool bw_summary             = false,
    bool stats                  = false,
    bool null                   = false,
    bool enable_size_map        = false,
    bool continue_on_bad_packet = false,
    bool compress_file			    = false)//RA
{
	std::string comp_ext =".gz";//RA
    unsigned long long num_total_samps = 0;
    // create a receive streamer
    uhd::stream_args_t stream_args(cpu_format, wire_format);
    std::vector<size_t> channel_nums;
    channel_nums.push_back(channel);
    stream_args.channels             = channel_nums;
    uhd::rx_streamer::sptr rx_stream = usrp->get_rx_stream(stream_args);

    uhd::rx_metadata_t md;
    std::vector<samp_type > buff(samps_per_buff);

    //////
    //File
    //////
    if(compress_file){
	     file +=comp_ext;
	    }
    std::ofstream outfile;
    if (not null){
        outfile.open(file.c_str(), std::ofstream::binary);
	     }

     //IPC file:
     std::ofstream comfile("/dev/shm/samplesToFile");
    typedef tee_device<ostream, ofstream> TeeDevice;
    typedef stream<TeeDevice> TeeStream;
    TeeDevice stream_tee(cout, comfile);
    TeeStream stream_split(stream_tee);
    //////
    //RA Adding Compression
    ///////
    boost::iostreams::filtering_streambuf<boost::iostreams::output> outbuf;
    if(compress_file){
		    outbuf.push(boost::iostreams::gzip_compressor());
	   }
    outbuf.push(outfile);
    //Convert streambuf to ostream
    std::ostream out(&outbuf);
    /////////////////////////////////////////////
    //Threading
    ////////////////////////////////////////////
  	concurrent_queue<std::vector<samp_type> > queue_data;
  	concurrent_queue<long> queue_size;
  	stream_split<<"Starting write"<<endl;
  	std::thread writeThread(writeToFile<samp_type>,
  				std::ref(out),std::ref(queue_size),
          std::ref(queue_data));
  	/////////
  	/////////
  	/////////
    // setup streaming
    uhd::stream_cmd_t stream_cmd((num_requested_samples == 0)
                                     ? uhd::stream_cmd_t::STREAM_MODE_START_CONTINUOUS
                                     : uhd::stream_cmd_t::STREAM_MODE_NUM_SAMPS_AND_DONE);
    stream_cmd.num_samps  = size_t(num_requested_samples);
    stream_cmd.stream_now = true;
    stream_cmd.time_spec  = uhd::time_spec_t();
    rx_stream->issue_stream_cmd(stream_cmd);

    typedef std::map<size_t, size_t> SizeMap;
    SizeMap mapSizes;
    const auto start_time = std::chrono::steady_clock::now();
    const auto stop_time =
        start_time + std::chrono::milliseconds(int64_t(1000 * time_requested));
    // Track time and samps between updating the BW summary
    auto last_update                     = start_time;
    unsigned long long last_update_samps = 0;
    unsigned long long clipping_total=0;
    unsigned long long overflow_total=0;
    double peak_tot =0 ;
    // Run this loop until either time expired (if a duration was given), until
    // the requested number of samples were collected (if such a number was
    // given), or until Ctrl-C was pressed.
    while (not stop_signal_called
           and (num_requested_samples != num_total_samps or num_requested_samples == 0)
           and (time_requested == 0.0 or std::chrono::steady_clock::now() <= stop_time)) {
        const auto now = std::chrono::steady_clock::now();

        size_t num_rx_samps =
            rx_stream->recv(&buff.front(), buff.size(), md, 3.0, enable_size_map);

        if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_TIMEOUT) {
            std::cerr << boost::format("Timeout while streaming") << std::endl;
            stop_signal_called =true;
            break;
        }
        if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_OVERFLOW) {
                std::cerr<<"OVF-restarting"<<std::endl;
                stream_cmd.time_spec=uhd::time_spec_t();
                overflow_occured++;
                rx_stream->issue_stream_cmd(stream_cmd); //restarting...
            continue;
        }
        if (md.error_code != uhd::rx_metadata_t::ERROR_CODE_NONE) {
            std::string error = str(boost::format("Receiver error: %s") % md.strerror());
            if (continue_on_bad_packet) {
                std::cerr << error << std::endl;
                continue;
            } else
                throw std::runtime_error(error);
        }

        if (enable_size_map) {
            SizeMap::iterator it = mapSizes.find(num_rx_samps);
            if (it == mapSizes.end())
                mapSizes[num_rx_samps] = 0;
            mapSizes[num_rx_samps] += 1;
        }

        num_total_samps += num_rx_samps;
        ////////////
        //Hand over to Thread
        ////////////
        if (not null){
	          queue_size.push(num_rx_samps * sizeof(samp_type));
	          queue_data.push(buff);
        }
        //Echo summary
        if (bw_summary) {
            last_update_samps += num_rx_samps;
            const auto time_since_last_update = now - last_update;
            if (time_since_last_update > std::chrono::seconds(1)) {
                const double time_since_last_update_s =
                    std::chrono::duration<double>(time_since_last_update).count();
                const double rate = double(last_update_samps) / time_since_last_update_s;

                clipping_total += clipping_occured;
                overflow_total +=overflow_occured;
                peak_tot = (peak > peak_tot) ? peak : peak_tot;
                stream_split <<"queue:"<<queue_data.size()
                          <<",clipp:"<<clipping_occured
                          <<",clipp_tot:"<<clipping_total
                          <<",ovf:"<<overflow_occured
                          <<",ovf_tot:"<<overflow_total
                          <<",peak:"<<peak
                          <<",peak_tot:"<<peak_tot
                          <<",rate:"<<(rate / 1e6)
                          <<",unit:\"Msps\""
                          <<std::endl;
                last_update_samps = 0;
                last_update       = now;
                clipping_occured = 0;
                overflow_occured = 0;
                peak=0;
            }
        }
    }
    const auto actual_stop_time = std::chrono::steady_clock::now();

    stream_cmd.stream_mode = uhd::stream_cmd_t::STREAM_MODE_STOP_CONTINUOUS;
    rx_stream->issue_stream_cmd(stream_cmd);

    //////////
    //Stop the thread:
    stop_signal_called = true;
    writeThread.join();
    stream_split<<"Write endend"<<endl;

    if (outfile.is_open()) {
      boost::iostreams::close(outbuf); // Don't forget this!
      outfile.close();
    }

    if (stats) {
        std::cout << std::endl;
        const double actual_duration_seconds =
            std::chrono::duration<float>(actual_stop_time - start_time).count();

        std::cout << boost::format("Received %d samples in %f seconds") % num_total_samps
                         % actual_duration_seconds
                  << std::endl;
        const double rate = (double)num_total_samps / actual_duration_seconds;
        std::cout << (rate / 1e6) << " Msps" << std::endl;
        std::cout << clipping_total << " Clipping" << std::endl;
        std::cout << overflow_total << " Overflow" << std::endl;
        std::cout << peak_tot << " Peak" << std::endl;


        if (enable_size_map) {
            std::cout << std::endl;
            std::cout << "Packet size map (bytes: count)" << std::endl;
            for (SizeMap::iterator it = mapSizes.begin(); it != mapSizes.end(); it++)
                std::cout << it->first << ":\t" << it->second << std::endl;
        }
    }
    comfile.close();
}

typedef std::function<uhd::sensor_value_t(const std::string&)> get_sensor_fn_t;

bool check_locked_sensor(std::vector<std::string> sensor_names,
    const char* sensor_name,
    get_sensor_fn_t get_sensor_fn,
    double setup_time)
{
    if (std::find(sensor_names.begin(), sensor_names.end(), sensor_name)
        == sensor_names.end()){
        return false;
    }

    auto setup_timeout = std::chrono::steady_clock::now()
                         + std::chrono::milliseconds(int64_t(setup_time * 1000));
    bool lock_detected = false;

    std::cout << boost::format("Waiting for \"%s\": ") % sensor_name;
    std::cout.flush();

    while (true) {
        if (lock_detected and (std::chrono::steady_clock::now() > setup_timeout)) {
            std::cout << " locked." << std::endl;
            break;
        }
        if (get_sensor_fn(sensor_name).to_bool()) {
            std::cout << "+";
            std::cout.flush();
            lock_detected = true;
        } else {
            if (std::chrono::steady_clock::now() > setup_timeout) {
                std::cout << std::endl;
                throw std::runtime_error(
                    str(boost::format(
                            "timed out waiting for consecutive locks on sensor \"%s\"")
                        % sensor_name));
            }
            std::cout << "_";
            std::cout.flush();
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    std::cout << std::endl;
    return true;
}

int UHD_SAFE_MAIN(int argc, char* argv[])
{
    // variables to be set by po
    std::string args, file, type, ant, subdev, ref, wirefmt;
    size_t channel, total_num_samps, spb;
    double rate, freq, gain, bw, total_time, setup_time, lo_offset,power_reference;

    // setup the program options
    po::options_description desc("Allowed options");
    // clang-format off
    desc.add_options()
        ("help", "help message")
        ("args", po::value<std::string>(&args)->default_value(""), "multi uhd device address args")
        ("file", po::value<std::string>(&file)->default_value("usrp_samples.dat"), "name of the file to write binary samples to")
        ("type", po::value<std::string>(&type)->default_value("short"), "sample type: double, float, or short")
        ("nsamps", po::value<size_t>(&total_num_samps)->default_value(0), "total number of samples to receive")
        ("duration", po::value<double>(&total_time)->default_value(0), "total number of seconds to receive")
        ("spb", po::value<size_t>(&spb)->default_value(10000), "samples per buffer")
        ("rate", po::value<double>(&rate)->default_value(1e6), "rate of incoming samples")
        ("freq", po::value<double>(&freq)->default_value(0.0), "RF center frequency in Hz")
        ("lo-offset", po::value<double>(&lo_offset)->default_value(0.0),
            "Offset for frontend LO in Hz (optional)")
        ("gain", po::value<double>(&gain), "gain for the RF chain")
        //("rpl", po::value<double>(&power_reference), "reference power level")
        ("ant", po::value<std::string>(&ant), "antenna selection")
        ("subdev", po::value<std::string>(&subdev), "subdevice specification")
        ("channel", po::value<size_t>(&channel)->default_value(0), "which channel to use")
        ("bw", po::value<double>(&bw), "analog frontend filter bandwidth in Hz")
        ("ref", po::value<std::string>(&ref)->default_value("internal"), "reference source (internal, external, mimo)")
        ("wirefmt", po::value<std::string>(&wirefmt)->default_value("sc16"), "wire format (sc8, sc16 or s16)")
        ("setup", po::value<double>(&setup_time)->default_value(1.0), "seconds of setup time")
        ("progress", "periodically display short-term bandwidth")
        ("stats", "show average bandwidth on exit")
        ("sizemap", "track packet size and display breakdown on exit")
        ("null", "run without writing to file")
        ("continue", "don't abort on a bad packet")
        ("skip-lo", "skip checking LO lock status")
        ("int-n", "tune USRP with integer-N tuning")
        ("compress", "Use Deflate to create compressed file") //RA
    ;
    // clang-format on
    po::variables_map vm;
    po::store(po::parse_command_line(argc, argv, desc), vm);
    po::notify(vm);

    // print the help message
    if (vm.count("help")) {
        std::cout << boost::format("UHD RX samples to file %s") % desc << std::endl;
        std::cout << std::endl
                  << "This application streams data from a single channel of a USRP "
                     "device to a file.\n"
                  << std::endl;
        return ~0;
    }

    bool bw_summary             = vm.count("progress") > 0;
    bool stats                  = vm.count("stats") > 0;
    bool null                   = vm.count("null") > 0;
    bool enable_size_map        = vm.count("sizemap") > 0;
    bool continue_on_bad_packet = vm.count("continue") > 0;
    bool compress_file			    = vm.count("compress") > 0; //RA

    if (compress_file){

    	std::cout<<"File compression active" << endl;
    }else{
    	std::cout<<"File compression NOT active"<<endl;
    }

    if (enable_size_map){
        std::cout << "Packet size tracking enabled - will only recv one packet at a time!"
                  << std::endl;
    }

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
    if (vm.count("subdev")){
        usrp->set_rx_subdev_spec(subdev);
    }

    std::cout << boost::format("Using Device: %s") % usrp->get_pp_string() << std::endl;

    // set the sample rate
    if (rate <= 0.0) {
        std::cerr << "Please specify a valid sample rate" << std::endl;
        return ~0;
    }
    std::cout << boost::format("Setting RX Rate: %f Msps...") % (rate / 1e6) << std::endl;
    usrp->set_rx_rate(rate, channel);
    std::cout << boost::format("Actual RX Rate: %f Msps...")
                     % (usrp->get_rx_rate(channel) / 1e6)
              << std::endl
              << std::endl;

    // set the center frequency
    if (vm.count("freq")) { // with default of 0.0 this will always be true
        std::cout << boost::format("Setting RX Freq: %f MHz...") % (freq / 1e6)
                  << std::endl;
        std::cout << boost::format("Setting RX LO Offset: %f MHz...") % (lo_offset / 1e6)
                  << std::endl;
        uhd::tune_request_t tune_request(freq, lo_offset);
        if (vm.count("int-n"))
            tune_request.args = uhd::device_addr_t("mode_n=integer");
        usrp->set_rx_freq(tune_request, channel);
        std::cout << boost::format("Actual RX Freq: %f MHz...")
                         % (usrp->get_rx_freq(channel) / 1e6)
                  << std::endl
                  << std::endl;
    }

    // set the rf gain
    if (vm.count("gain")) {
        std::cout << boost::format("Setting RX Gain: %f dB...") % gain << std::endl;
        usrp->set_rx_gain(gain, channel);
        std::cout << boost::format("Actual RX Gain: %f dB...")
                         % usrp->get_rx_gain(channel)
                  << std::endl
                  << std::endl;
    }

    /*if (vm.count("rpl")) {
        std::cout << boost::format("Setting RX Power Level: %f dB...") % power_reference << std::endl;
        //std::cout << "RPEV RPL"<<usrp->get_rx_power_reference(channel) << '\n';
        usrp->set_rx_power_reference(power_reference, channel);
        std::cout << boost::format("Actual RX Power Level: %f dB...")
                         % usrp->get_rx_power_reference(channel)
                  << std::endl
                  << std::endl;
    }*/

    // set the IF filter bandwidth
    if (vm.count("bw")) {
        std::cout << boost::format("Setting RX Bandwidth: %f MHz...") % (bw / 1e6)
                  << std::endl;
        usrp->set_rx_bandwidth(bw, channel);
        std::cout << boost::format("Actual RX Bandwidth: %f MHz...")
                         % (usrp->get_rx_bandwidth(channel) / 1e6)
                  << std::endl
                  << std::endl;
    }

    // set the antenna
    if (vm.count("ant")){
        usrp->set_rx_antenna(ant, channel);
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(int64_t(1000 * setup_time)));

    // check Ref and LO Lock detect
    if (not vm.count("skip-lo")) {
        check_locked_sensor(usrp->get_rx_sensor_names(channel),
            "lo_locked",
            [usrp, channel](const std::string& sensor_name) {
                return usrp->get_rx_sensor(sensor_name, channel);
            },
            setup_time);
        if (ref == "mimo") {
            check_locked_sensor(usrp->get_mboard_sensor_names(0),
                "mimo_locked",
                [usrp](const std::string& sensor_name) {
                    return usrp->get_mboard_sensor(sensor_name);
                },
                setup_time);
        }
        if (ref == "external") {
            check_locked_sensor(usrp->get_mboard_sensor_names(0),
                "ref_locked",
                [usrp](const std::string& sensor_name) {
                    return usrp->get_mboard_sensor(sensor_name);
                },
                setup_time);
        }
    }

    if (total_num_samps == 0) {
        std::signal(SIGINT, &sig_int_handler);
        std::cout << "Press Ctrl + C to stop streaming..." << std::endl;
    }

#define recv_to_file_args(format) \
    (usrp,                        \
        format,                   \
        wirefmt,                  \
        channel,                  \
        file,                     \
        spb,                      \
        total_num_samps,          \
        total_time,               \
        bw_summary,               \
        stats,                    \
        null,                     \
        enable_size_map,          \
        continue_on_bad_packet,	  \
        compress_file) // recv to file
    if (wirefmt == "s16") {
        if (type == "double")
            recv_to_file<double> recv_to_file_args("f64");
        else if (type == "float")
            recv_to_file<float> recv_to_file_args("f32");
        else if (type == "short")
            recv_to_file<short> recv_to_file_args("s16");
        else
            throw std::runtime_error("Unknown type " + type);
    } else {
        if (type == "double")
            recv_to_file<std::complex<double>> recv_to_file_args("fc64");
        else if (type == "float")
            recv_to_file<std::complex<float>> recv_to_file_args("fc32");
        else if (type == "short")
            recv_to_file<std::complex<short>> recv_to_file_args("sc16");
        else
            throw std::runtime_error("Unknown type " + type);
    }
    // finished
    std::cout << std::endl << "Done!" << std::endl << std::endl;

    return EXIT_SUCCESS;
}
