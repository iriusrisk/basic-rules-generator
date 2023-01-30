import argparse
import logging
import os
import pandas as pd
import requests
import sys
from lxml import etree

# Config #

# Logger
logging.basicConfig(filename="logFile.log",
                    format='%(asctime)s  %(levelname)-10s %(message)s',
                    datefmt="%Y-%m-%d-%H-%M-%S",
                    filemode='w')
log = logging.getLogger()
log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.INFO)

# Argument parser
p = argparse.ArgumentParser()

# Mandatory parameters
# The file where the countermeasures are listed
p.add_argument('--input', type=str)
# How the countermeasure will be set: "required" or "implemented"
p.add_argument('--mode', type=str)

# Select one:
# Option 1: Access to an IriusRisk instance to get where do the countermeasures live
p.add_argument('--url', type=str, nargs="?")
p.add_argument('--token', type=str, nargs="?")
# Option 2: Get where the countermeasures live from a folder with the libraries
p.add_argument('--libs', type=str, nargs="?")

args = p.parse_args()

LIBS_FOLDER = args.libs
IRIUS_URL = args.url
IRIUS_TOKEN = args.token
INPUT_FILE = args.input
MODE = args.mode
COMPANY_NAME = "Company"


#

def read_input_file(file):
    """
    Reads the input file and extracts the countermeasures
    :param file: input file in several formats (csv, txt, xlsx, xlsx...)
    :return: a set with the refs of the countermeasures
    """
    required = set()
    if file.endswith(('.csv', '.txt')):
        with open(file, "r") as ff:
            for element in ff.read().splitlines():
                required.add(element)
    if file.endswith(('.xls', '.xlsx')):
        sheet_to_df_map = pd.read_excel(file, sheet_name=None)
        for k, v in sheet_to_df_map.items():
            ref_list = v["Ref"].to_list()
            cleaned_list = [x for x in ref_list if str(x) != 'nan']
            required.update(cleaned_list)

    return required


def get_library_countermeasure_map(folder):
    """
    If URL+Token is detected this method will query the IriusRisk API to get the information about the libraries.
    If a folder path is passed in then the information will be retrieved from the XMLs.
    :return: a map with the libraries and all the countermeasures that are inside each one of them
    """
    lib_map = dict()

    if folder:
        for filename in os.listdir(str(folder)):
            f = os.path.join(folder, filename)
            if os.path.isfile(f) and f.endswith(".xml"):
                tree = etree.parse(f)
                root = tree.getroot()
                lib = root.attrib["ref"]

                lib_map[lib] = set()
                for rp in root.find("riskPatterns").iter("riskPattern"):
                    for c in rp.find("countermeasures").iter("countermeasure"):
                        lib_map[lib].add(c.attrib["ref"])
                log.info(f"Detected {len(lib_map[lib])} countermeasures in {lib}...")
    else:
        header = {"api-token": IRIUS_TOKEN}

        response = requests.get(IRIUS_URL + "/api/v1/libraries", headers=header)
        all_libraries_data = response.json()
        for e in all_libraries_data:
            response2 = requests.get(IRIUS_URL + "/api/v1/libraries/" + e["ref"], headers=header)
            library_data = response2.json()
            lib = e['ref']
            lib_map[lib] = set()
            for rp in library_data["riskPatterns"]:
                for c in rp["countermeasures"]:
                    lib_map[lib].add(c["ref"])

            log.info(f"Detected {len(lib_map[lib])} countermeasures in {lib}...")

    return lib_map


def get_lib_for_countermeasure(ref, lib_map):
    """
    Since the countermeasure can live in more than one library this method ensures that the chosen library is the one that has the most number of countermeasures
    :param ref:
    :param lib_map:
    :return:
    """
    options = set([k for k, v in lib_map.items() if ref in v])
    lib_name, number = ("", 0)
    if len(options) > 0:
        lib_name, number = max([(k, len(v)) for k, v in lib_map.items() if k in options], key=lambda item: item[1])

    return lib_name


def main():
    # Getting list of countermeasures
    list_of_countermeasures = read_input_file(INPUT_FILE)
    if len(list_of_countermeasures) > 0:
        log.info(f"Detected {len(list_of_countermeasures)} to mark as {MODE}")
    else:
        log.error(f"No values have been detected in {INPUT_FILE}. Exiting...")
        exit(-1)

    # Detecting mode
    action_mode = ""
    if MODE == "required":
        action_mode = "APPLY_CONTROL"
    if MODE == "implemented":
        action_mode = "IMPLEMENT_CONTROL"
    if action_mode == "":
        log.error("No action has been indicated on --mode parameter. Exiting...")
        exit(-1)

    # Getting list of libraries for countermeasures
    lib_map = {}
    if IRIUS_URL and IRIUS_TOKEN:
        lib_map = get_library_countermeasure_map(None)
    elif LIBS_FOLDER:
        lib_map = get_library_countermeasure_map(LIBS_FOLDER)
    else:
        log.error("No values have been indicated on --url/token or --libs. Exiting...")
        exit(-1)

    # Generating rules
    already_added = set()
    not_added = set()
    with open("rules.txt", "w") as output:
        for control in list_of_countermeasures:
            libname = get_lib_for_countermeasure(control, lib_map)
            if libname != "":
                rulename = f'{COMPANY_NAME} - Mark as {MODE} - {control}'
                conditions = '<condition name="CONDITION_IS_IN_TRUSTZONE" field="id" value="aaaaaaaa-bbbb-cccc-dddd-eeeeffff0000_::_trust-zone"/>'
                actions = f'<action project="{libname}" value="{control}_::_false" name="{action_mode}"/>'
                result = f'<rule name="{rulename}" module="component" generatedByGui="true"><conditions>{conditions}</conditions><actions>{actions}</actions></rule>'
                log.info(result)
                already_added.add(control)

                output.write(result + "\n")
            else:
                not_added.add(control)

        log.info(
            f"Finished! Added {len(already_added)} rules. You just need to copy the output from the rules.txt file to your library.")
        log.info(f"List of all countermeasures detected:  {sorted(list_of_countermeasures)}")
        log.info(f"List of all countermeasures added:     {sorted(already_added)}")
        log.info(f"List of all countermeasures not added: {sorted(not_added)}")


if __name__ == "__main__":
    main()
