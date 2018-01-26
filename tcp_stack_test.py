#!/usr/bin/env python

import unittest
import os
import argparse
import yaml
from iperf3_tc import Iperf3TestCase
from tcpkali_tc import tcpkali_TestCase
from cpu_affinity import Affinity

ATTR_NO_VPP = '--no-vpp'
USE_VPP = True
logdir = "/tmp"
procdist = None
corelist = corelist_client = None
skip_cores = None

cases = {
    "ls": Affinity.case_ls,
    "ps": Affinity.case_ps,
    "ns": Affinity.case_ns,
    "nn": Affinity.case_nn
}

logfiles = {
    "vpp": {
        "log": "vpp_log.txt",
        "memory_log": "vpp_mem_log.txt"
    },
    "iperf3": {
        "server_log": "iperf3_server_log.txt",
        "server_mem_log": "iperf3_server_mem_log.txt",
        "client_log": "iperf3_client_log.txt",
        "client_mem_log": "iperf3_client_mem_log.txt",
        "client_json_out": ""
    }
}


def build_suite(config):
    suite = unittest.TestSuite()
    if config['iperf3']['enable']:
        suite.addTest(Iperf3TestCase(
            config,
            use_vpp=USE_VPP,
            corelist=corelist,
            corelist_client=corelist_client))
    if config['tcpkali']['enable']:
        suite.addTest(tcpkali_TestCase(config))
    return suite


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VCL test script.",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--no_vpp", action='store_true',
        help="Run test without VCL preload.")
    parser.add_argument(
        "--logdir", type=str, metavar="path",
        help="Where to place output log files.\n"
        "If not specified, will use configuration from config.yml")
    parser.add_argument(
        "--procdist", type=str, help="Specify distribution of "
        "client/server process pairs\n "
        "across CPUs and NUMA nodes. Available options:"
        "\nls   share one logical core"
        "\nps   share one physical core (Hyperthreading pair)"
        "\nns   share the same NUMA node, different phys cores"
        "\nnn   run on separate NUMA nodes")
    parser.add_argument(
        "--skip_cores", type=str, metavar="x,y-z",
        help="Specify logical CPUs to exclude,\n"
             "as comma separated list of distinct core IDs or ranges\n"
             "Will also exclude the specified cores' Hyperthreading twins.")
    parser.add_argument(
        "--reuse", action="store_true",
        help="More aggressively reuse CPUs. Every logical CPU\n"
             "(except skipped) will run one server and one client\n"
             " from different pairs.")

    args = parser.parse_args()
    if args.no_vpp:
        USE_VPP = False
    if args.logdir:
        logdir = args.logdir
    if args.procdist:
        procdist = args.procdist
    if procdist not in cases.keys():
        raise ValueError("Unrecognized value for option --procdist. "
                         "Available options are: {0}".format(cases.keys()))
    if args.skip_cores:
        skip_cores = Affinity.parse_cores(args.skip_cores)

    # read config file
    test_config_file = os.getcwd() + "/config.yml"
    with open(test_config_file, 'r') as ymlf:
        test_config = yaml.load(ymlf)

    # override logfile location
    test_config["global"]["test_result_dir"] = logdir
    for log in logfiles["vpp"].keys():
        test_config["vpp"][log] = "{0}/{1}".format(
            logdir, logfiles["vpp"][log])
    for log in logfiles["iperf3"].keys():
        test_config["iperf3"][log] = "{0}/{1}".format(
            logdir, logfiles["iperf3"][log])

    # Generate corelists for client and server processes
    ht_pairs = Affinity.get_ht_pairs(skip_cores)

    if procdist == "ps" or args.reuse:
        for cores in ht_pairs.values():
            if len(cores) < 2:
                raise RuntimeError(
                    "Hyperthreading not active on all cores.")

    if len(ht_pairs.keys()) < 2 and procdist in ("ns", "nn"):
        raise RuntimeError(
            "Cross-physcore testcase specified but only one physical core "
            "was detected.")

    numa_topology = Affinity.get_numa_topo(ht_pairs)

    if procdist == "nn" and numa_topology is None:
        raise RuntimeError(
            "Cross-NUMA testcase specified but only one NUMA node "
            "was detected.")

    corelist, corelist_client = cases[procdist](
        ht_pairs,
        numa_topology,
        reuse=True if args.reuse else False
    )

    if len(corelist) != len(corelist_client):
        raise RuntimeError("Server/Client CPU list length mismatch.")

    # Run the tests
    runner = unittest.TextTestRunner()
    test_suite = build_suite(test_config)
    runner.run(test_suite)
