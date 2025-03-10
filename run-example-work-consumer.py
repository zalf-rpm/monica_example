#!/usr/bin/python
# -*- coding: UTF-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/. */

# Authors:
# Michael Berg-Mohnicke <michael.berg@zalf.de>
#
# Maintainers:
# Currently maintained by the authors.
#
# This file has been created at the Institute of
# Landscape Systems Analysis at the ZALF.
# Copyright (C: Leibniz Centre for Agricultural Landscape Research (ZALF)

import sys
#sys.path.insert(0, "C:\\Users\\berg.ZALF-AD\\GitHub\\monica\\project-files\\Win32\\Release")
#sys.path.insert(0, "C:\\Users\\berg.ZALF-AD\\GitHub\\monica\\src\\python")
#sys.path.insert(0, "C:\\Program Files (x86)\\MONICA")
#print sys.path

import gc
import csv
import types
import os
import json
import timeit
from datetime import datetime
from collections import defaultdict, OrderedDict
import numpy as np

import zmq
#print "pyzmq version: ", zmq.pyzmq_version(), " zmq version: ", zmq.zmq_version()

import monica_io3
#print "path to monica_io: ", monica_io.__file__
import monica_run_lib as Mrunlib

LOCAL_RUN = True

PATHS = {
    "container": {
        "local-path-to-data-dir": "/monica-data/data/", # mounted data dir 
        "local-path-to-output-dir": "/monica-output/out/", # mounted out dir
        "local-path-to-csv-output-dir": "/monica-output/csv-out/" # mounted output dir for csv files
    },
    "local": {
        "local-path-to-data-dir": "C:/zalf-rpm/monica_example/monica-data/data/",
        "local-path-to-output-dir": "C:/zalf-rpm/monica_example/out/",
        "local-path-to-csv-output-dir": "C:/zalf-rpm/monica_example/csv-out/"
    },
    "remote": {
        "local-path-to-data-dir": "D:/awork/zalf/monica/monica_example/monica-data/data/",
        "local-path-to-output-dir": "D:/awork/zalf/monica/monica_example/out/",
        "local-path-to-csv-output-dir": "D:/awork/zalf/monica/monica_example/csv-out/"
    }
}
LOCAL_RUN_HOST = "login01.cluster.zalf.de" #"localhost"
PORT = "7779"
TEMPLATE_SOIL_PATH = "{local_path_to_data_dir}germany/buek1000_1000_gk5.asc"

def create_output(result):
    "create output structure for single run"

    cm_count_to_vals = defaultdict(dict)
    if len(result.get("data", [])) > 0 and len(result["data"][0].get("results", [])) > 0:

        for data in result.get("data", []):
            results = data.get("results", [])
            oids = data.get("outputIds", [])

            #skip empty results, e.g. when event condition haven't been met
            if len(results) == 0:
                continue

            assert len(oids) == len(results)
            for kkk in range(0, len(results[0])):
                vals = {}

                for iii in range(0, len(oids)):
                    oid = oids[iii]
                    val = results[iii][kkk]

                    name = oid["name"] if len(oid["displayName"]) == 0 else oid["displayName"]

                    if isinstance(val, list):
                        for val_ in val:
                            vals[name] = val_
                    else:
                        vals[name] = val

                if "CM-count" not in vals:
                    print("Missing CM-count in result section. Skipping results section.")
                    continue

                cm_count_to_vals[vals["CM-count"]].update(vals)
    

    for cmc in sorted(cm_count_to_vals.keys()):
        if cm_count_to_vals[cmc]["last-doy"] >= 365:
            del cm_count_to_vals[cmc]

    return cm_count_to_vals


def write_row_to_grids(row_col_data, row, ncols, header, path_to_output_dir, path_to_csv_output_dir, setup_id):
    "write grids row by row"
    
    if row in row_col_data:
        is_data_row = len(list(filter(lambda x: x != -9999, row_col_data[row].values()))) > 0
        if is_data_row:
            path_to_row_file = path_to_csv_output_dir + "row-" + str(row) + ".csv" 

            if not os.path.isfile(path_to_row_file):
                with open(path_to_row_file, "w") as _:
                    _.write("CM-count,row,col,Crop,Year,\
                    Globrad-sum,Tavg,Precip-sum,LAI-max,Yield-last,\
                    GPP-sum,NPP-sum,NEP-sum,Ra-sum,Rh-sum,G-iso,G-mono,Cycle-length,\
                    AbBiom-final,TraDef-avg,Stage-harv\n")

            with open(path_to_row_file, 'a') as _:
                writer = csv.writer(_, delimiter=",")

                for col in range(0, ncols):
                    if col in row_col_data[row]:
                        rcd_val = row_col_data[row][col]
                        if rcd_val != -9999 and len(rcd_val) > 0:
                            cell_data = rcd_val[0]

                            for cm_count, data in cell_data.items():
                                row_ = [
                                    cm_count,
                                    row,
                                    col,
                                    data["Crop"],
                                    data["Year"],
                                    data["Globrad-sum"],
                                    data["Tavg"],
                                    data["Precip-sum"],
                                    data["LAI-max"],
                                    data["Yield-last"],
                                    data["GPP-sum"],
                                    data["NPP-sum"],
                                    data["NEP-sum"],
                                    data["Ra-sum"],
                                    data["Rh-sum"],
                                    data["G-iso"],
                                    data["G-mono"],
                                    data["Cycle-length"]#,

                                    #data["AbBiom-final"],
                                    #data["TraDef-avg"],
                                    #data["Stage-harv"]
                                ]
                                writer.writerow(row_)


    if not hasattr(write_row_to_grids, "nodata_row_count"):
        write_row_to_grids.nodata_row_count = defaultdict(lambda: 0)
        write_row_to_grids.list_of_output_files = defaultdict(list)

    make_dict_nparr = lambda: defaultdict(lambda: np.full((ncols,), -9999, dtype=np.float))

    output_grids = {
        "Globrad-sum": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "Tavg": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "Precip-sum": {"data" : make_dict_nparr(), "cast-to": "int"},
        "LAI-max": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "Yield-last": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "GPP-sum": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "NPP-sum": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "NEP-sum": {"data" : make_dict_nparr(), "cast-to": "int"},
        "Ra-sum": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "Rh-sum": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "G-iso": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "G-mono": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        "Cycle-length": {"data" : make_dict_nparr(), "cast-to": "int"},

        #"AbBiom-final": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 1},
        #"TraDef-avg": {"data" : make_dict_nparr(), "cast-to": "float", "digits": 3},
        #"Stage-harv": {"data" : make_dict_nparr(), "cast-to": "int"}
    }

    cmc_to_crop = {}

    is_no_data_row = True
    # skip this part if we write just a nodata line
    if row in row_col_data:
        no_data_cols = 0
        for col in range(0, ncols):
            if col in row_col_data[row]:
                rcd_val = row_col_data[row][col]
                if rcd_val == -9999:
                    no_data_cols += 1
                    continue
                else:
                    cmc_and_year_to_vals = defaultdict(lambda: defaultdict(list))
                    for cell_data in rcd_val:
                        for cm_count, data in cell_data.items():
                            for key, val in output_grids.items():
                                if cm_count not in cmc_to_crop:
                                    cmc_to_crop[cm_count] = data["Crop"]

                                if key in data:
                                    cmc_and_year_to_vals[(cm_count, data["Year"])][key].append(data[key])
                                else:
                                    cmc_and_year_to_vals[(cm_count, data["Year"])][key] #just make sure at least an empty list is in there

                    for (cm_count, year), key_to_vals in cmc_and_year_to_vals.items():
                        for key, vals in key_to_vals.items():
                            output_vals = output_grids[key]["data"]
                            if len(vals) > 0:
                                output_vals[(cm_count, year)][col] = sum(vals) / len(vals)
                            else:
                                output_vals[(cm_count, year)][col] = -9999
                                #no_data_cols += 1

        is_no_data_row = no_data_cols == ncols

    if is_no_data_row:
        write_row_to_grids.nodata_row_count[setup_id] += 1

    def write_nodata_rows(file_):
        for _ in range(write_row_to_grids.nodata_row_count[setup_id]):
            rowstr = " ".join(["-9999" for __ in range(ncols)])
            file_.write(rowstr +  "\n")

    for key, y2d_ in output_grids.items():

        y2d = y2d_["data"]
        cast_to = y2d_["cast-to"]
        digits = y2d_.get("digits", 0)
        if cast_to == "int":
            mold = lambda x: str(int(x))
        else:
            mold = lambda x: str(round(x, digits))

        for (cm_count, year), row_arr in y2d.items():

            crop = cmc_to_crop[cm_count]    
            crop = crop.replace("/", "").replace(" ", "")
            path_to_file = path_to_output_dir + crop + "_" + key + "_" + str(year) + "_" + str(cm_count) + ".asc"

            if not os.path.isfile(path_to_file):
                with open(path_to_file, "w") as _:
                    _.write(header)
                    write_row_to_grids.list_of_output_files[setup_id].append(path_to_file)

            with open(path_to_file, "a") as file_:
                write_nodata_rows(file_)
                rowstr = " ".join(["-9999" if int(x) == -9999 else mold(x) for x in row_arr])
                file_.write(rowstr +  "\n")

    # clear the no-data row count when no-data rows have been written before a data row
    if not is_no_data_row:
        write_row_to_grids.nodata_row_count[setup_id] = 0

    # if we're at the end of the output and just empty lines are left, then they won't be written in the
    # above manner because there won't be any rows with data where they could be written before
    # so add no-data rows simply to all files we've written to before
    if is_no_data_row \
    and write_row_to_grids.list_of_output_files[setup_id] \
    and write_row_to_grids.nodata_row_count[setup_id] > 0:
        for path_to_file in write_row_to_grids.list_of_output_files[setup_id]:
            with open(path_to_file, "a") as file_:
                write_nodata_rows(file_)
        write_row_to_grids.nodata_row_count[setup_id] = 0
    
    if row in row_col_data:
        del row_col_data[row]


def run_consumer(leave_after_finished_run = True, server = {"server": None, "port": None}, shared_id = None):
    "collect data from workers"

    config = {
        "user": "remote" if LOCAL_RUN else "container",
        "port": server["port"] if server["port"] else PORT,
        "server": server["server"] if server["server"] else LOCAL_RUN_HOST, 
        "start-row": "0",
        "end-row": "-1",
        "shared_id": shared_id,
        "no-of-setups": 2 #None
    }
    config["out"] = PATHS[config["user"]]["local-path-to-output-dir"]
    config["csv-out"] = PATHS[config["user"]]["local-path-to-csv-output-dir"]

    if len(sys.argv) > 1 and __name__ == "__main__":
        for arg in sys.argv[1:]:
            k,v = arg.split("=")
            if k in config:
                config[k] = v

    print("consumer config:", config)

    context = zmq.Context()
    if config["shared_id"]:
        socket = context.socket(zmq.DEALER)
        socket.setsockopt(zmq.IDENTITY, config["shared_id"])
    else:
        socket = context.socket(zmq.PULL)

    socket.connect("tcp://" + config["server"] + ":" + config["port"])

    leave = False
    write_normal_output_files = False

    path_to_soil_grid = TEMPLATE_SOIL_PATH.format(local_path_to_data_dir=PATHS[config["user"]]["local-path-to-data-dir"])
    soil_metadata, header = Mrunlib.read_header(path_to_soil_grid)
    soil_grid_template = np.loadtxt(path_to_soil_grid, dtype=int, skiprows=6)
    #set invalid soils / water to no-data
    soil_grid_template[soil_grid_template < 1] = -9999
    soil_grid_template[soil_grid_template > 71] = -9999
    #set all data values to one, to count them later
    soil_grid_template[soil_grid_template != -9999] = 1
    #set all no-data values to 0, to ignore them while counting
    soil_grid_template[soil_grid_template == -9999] = 0
    #count cols in rows
    datacells_per_row = np.sum(soil_grid_template, axis=1)

    start_row = int(config["start-row"])
    end_row = int(config["end-row"])
    ncols = int(soil_metadata["ncols"])
    setup_id_to_data = defaultdict(lambda: {
        "start_row": start_row,
        "end_row": end_row,
        "nrows": end_row - start_row + 1 if start_row > 0 and end_row >= start_row else int(soil_metadata["nrows"]),
        "ncols": ncols,
        "header": header,
        "out_dir_exists": False,
        "row-col-data": defaultdict(lambda: defaultdict(list)),
        "datacell-count": datacells_per_row.copy(),
        "next-row": start_row
    })

    def process_message(msg):

        if not hasattr(process_message, "wnof_count"):
            process_message.wnof_count = 0
            process_message.setup_count = 0

        leave = False

        if msg["type"] == "finish":
            print("c: received finish message")
            leave = True
 
        elif not write_normal_output_files:
            custom_id = msg["customId"]
            setup_id = custom_id["setup_id"]

            data = setup_id_to_data[setup_id]

            row = custom_id["srow"]
            col = custom_id["scol"]
            #crow = custom_id.get("crow", -1)
            #ccol = custom_id.get("ccol", -1)
            #soil_id = custom_id.get("soil_id", -1)

            debug_msg = "received work result " + str(process_message.received_env_count) + " customId: " + str(msg.get("customId", "")) \
            + " next row: " + str(data["next-row"]) \
            + " cols@row to go: " + str(data["datacell-count"][row]) + "@" + str(row) + " cells_per_row: " + str(datacells_per_row[row])#\
            #+ " rows unwritten: " + str(data["row-col-data"].keys()) 
            print(debug_msg)
            #debug_file.write(debug_msg + "\n")
            data["row-col-data"][row][col].append(create_output(msg))
            data["datacell-count"][row] -= 1

            process_message.received_env_count = process_message.received_env_count + 1

            #while data["next-row"] in data["row-col-data"] and data["datacell-count"][data["next-row"]] == 0:
            while data["datacell-count"][data["next-row"]] == 0:
                
                path_to_out_dir = config["out"] + str(setup_id) + "/"
                path_to_csv_out_dir = config["csv-out"] + str(setup_id) + "/"
                if not data["out_dir_exists"]:
                    if os.path.isdir(path_to_out_dir) and os.path.exists(path_to_out_dir):
                        data["out_dir_exists"] = True
                    else:
                        try:
                            os.makedirs(path_to_out_dir)
                            data["out_dir_exists"] = True
                        except OSError:
                            print("c: Couldn't create dir:", path_to_out_dir, "! Exiting.")
                            exit(1)
                    if os.path.isdir(path_to_csv_out_dir) and os.path.exists(path_to_csv_out_dir):
                        data["out_dir_exists"] = True
                    else:
                        try:
                            os.makedirs(path_to_csv_out_dir)
                            data["out_dir_exists"] = True
                        except OSError:
                            print("c: Couldn't create dir:", path_to_csv_out_dir, "! Exiting.")
                            exit(1)
                
                write_row_to_grids(data["row-col-data"], data["next-row"], data["ncols"], data["header"], path_to_out_dir, path_to_csv_out_dir, setup_id)
                
                debug_msg = "wrote row: "  + str(data["next-row"]) + " next-row: " + str(data["next-row"]+1) + " rows unwritten: " + str(data["row-col-data"].keys())
                print(debug_msg)
                #debug_file.write(debug_msg + "\n")
                
                data["next-row"] += 1 # move to next row (to be written)

                if leave_after_finished_run \
                and ((data["end_row"] < 0 and data["next-row"] > data["nrows"]-1) \
                    or (data["end_row"] >= 0 and data["next-row"] > data["end_row"])): 
                    
                    process_message.setup_count += 1
                    # if all setups are done, the run_setups list should be empty and we can return
                    if process_message.setup_count >= int(config["no-of-setups"]):
                        print("c: all results received, exiting")
                        leave = True
                        break
                
        elif write_normal_output_files:

            if msg.get("type", "") in ["jobs-per-cell", "no-data", "setup_data"]:
                #print "ignoring", result.get("type", "")
                return

            print("received work result ", process_message.received_env_count, " customId: ", str(msg.get("customId", "").values()))

            custom_id = msg["customId"]
            setup_id = custom_id["setup_id"]
            row = custom_id["srow"]
            col = custom_id["scol"]
            #crow = custom_id.get("crow", -1)
            #ccol = custom_id.get("ccol", -1)
            #soil_id = custom_id.get("soil_id", -1)
            
            process_message.wnof_count += 1

            #with open("out/out-" + str(i) + ".csv", 'wb') as _:
            with open("out-normal/out-" + str(process_message.wnof_count) + ".csv", 'wb') as _:
                writer = csv.writer(_, delimiter=",")

                for data_ in msg.get("data", []):
                    results = data_.get("results", [])
                    orig_spec = data_.get("origSpec", "")
                    output_ids = data_.get("outputIds", [])

                    if len(results) > 0:
                        writer.writerow([orig_spec.replace("\"", "")])
                        for row in monica_io.write_output_header_rows(output_ids,
                                                                      include_header_row=True,
                                                                      include_units_row=True,
                                                                      include_time_agg=False):
                            writer.writerow(row)

                        for row in monica_io.write_output(output_ids, results):
                            writer.writerow(row)

                    writer.writerow([])

            process_message.received_env_count = process_message.received_env_count + 1

        return leave

    process_message.received_env_count = 1

    while not leave:
        try:
            start_time_recv = timeit.default_timer()
            msg = socket.recv_json(encoding="latin-1")
            elapsed = timeit.default_timer() - start_time_recv
            print("time to receive message" + str(elapsed))
            start_time_proc = timeit.default_timer()
            leave = process_message(msg)
            elapsed = timeit.default_timer() - start_time_proc
            print("time to process message" + str(elapsed))
        except Exception as e:
            print("Exception:", e)
            continue

    print("exiting run_consumer()")
    #debug_file.close()

if __name__ == "__main__":
    run_consumer()
#main()


