"""
This script can take a data directory of TERRA data and create Clowder datasets, clean metadata, and upload files.

If the data is Level_1 or higher, will look for a _cleaned.json file and attempt to look in corresponding raw_data
directory for metadata if the _cleaned file is missing.

Expects sensor-metadata git directory to be available locally for fixed metadata:
    git clone https://github.com/terraref/sensor-metadata.git
    export SENSOR_METADATA_CACHE=/path/to/sensor-metadata

Expected data directory structure:
    /root_path
        /raw_data
            /stereoTop
                /YYYY-MM-DD
                    /YYYY-MM-DD__HH-MM-SS-sss
                        /...file.bin
                        /..._metadata.json
        /Level_1
            /rgb_geotiff
                /YYYY-MM-DD
                    /YYYY-MM-DD__HH-MM-SS-sss
                        /...file.tif
        /Level_2
            ...

If a season folder is introduced (e.g. season10) at some level, script will need to be updated.
"""

import os, requests, json
from pyclowder.connectors import Connector
from terrautils.extractors import load_json_file, build_dataset_hierarchy_crawl, upload_to_dataset
from terrautils.metadata import clean_metadata, get_season_and_experiment


# Set to True to test reading & cleaning a dataset from each product without actually uploading
dry_run = True

# ---------------------------------
# Clowder instance configuration
# ---------------------------------
clowder_host = "https://terraref.ncsa.illinois.edu/clowder"
clowder_admin_key = "SECRET_KEY"
# The following user will be shown as the creator and owner of uploaded datasets
clowder_user   = "terrarefglobus+uamac@ncsa.illinois.edu"
clowder_pass   = "PASSWORD"
clowder_userid = "57adcb81c0a7465986583df1"
# The following space in Clowder will contain all uploaded datasets and collections
clowder_space = "571fb3e1e4b032ce83d95ecf"
# Mapping of local files to the Clowder directory if mounts are different
conn = Connector("", {}, mounted_paths={"/home/clowder/sites":"/home/clowder/sites"})

# ---------------------------------
# Filesystem configuration
# ---------------------------------
root_path = "/home/clowder/sites/ua-mac"

# Defines which products to upload (i.e. remove raw_data key to only upload Level_1 data)
# TODO: Currently only supports products with a timestamp level (i.e. EnvironmentLogger will not work)
products_to_upload = {
    "raw_data": ["stereoTop", "flirIrCamera"],
    "Level_1": ["rgb_geotiff", "ir_geotiff"]
}

# Defines start and end date to upload (inclusive)
start_date = "2019-06-01"
end_date   = "2019-06-05"


# Upload a dataset to Clowder including metadata, etc.
def upload_dataset(dataset_path, level, product, timestamp, sess, logfile):
    contents = os.listdir(dataset_path)
    if len(contents) == 0:
        logfile.write('%s,%s,"%s",%s\n' % (level, product, dataset_path, "ERR: No files found"))
        return False

    # Find and prepare the metadata
    clean_md = None
    for f in contents:
        if f.endswith("_metadata.json"):
            md = load_json_file(os.path.join(dataset_path, f))
            clean_md = clean_metadata(md, product)
        elif f.endswith("_metadata_cleaned.json"):
            clean_md = load_json_file(os.path.join(dataset_path, f))

    if clean_md is None:
        logfile.write('%s,%s,"%s",%s\n' % (level, product, dataset_path, "ERR: No metadata found"))
        return False

    # Create the dataset in Clowder
    season_name, experiment_name, updated_experiment = get_season_and_experiment(timestamp, product, clean_md)
    YYYY = timestamp[:4]
    MM   = timestamp[5:7]
    DD   = timestamp[8:10]
    dataset_name = "%s - %s" % (product, timestamp)
    if not dry_run:
        dsid = build_dataset_hierarchy_crawl(clowder_host, clowder_admin_key, clowder_user, clowder_pass, clowder_space,
                                             season_name, experiment_name, product, YYYY, MM, DD, dataset_name)
        logfile.write('%s,%s,"%s",%s\n' % (level, product, dataset_path, "OK: %s" % dsid))

    # Upload metadata
    if not dry_run:
        sess.post("%s/api/datasets/%s/metadata.jsonld" % (clowder_host, dsid),
                  headers={'Content-Type':'application/json'},
                  data=json.dumps({
                      "@context": ["https://clowder.ncsa.illinois.edu/contexts/metadata.jsonld",
                                   {"@vocab": "https://terraref.ncsa.illinois.edu/metadata/uamac#"}],
                      "content": clean_md,
                      "agent": {
                          "@type": "cat:user",
                          "user_id": "https://terraref.ncsa.illinois.edu/clowder/api/users/%s" % clowder_userid
                      }
                  }))
    else:
        print("%s metadata successfully cleaned." % dataset_path)

    # Add each file
    for f in contents:
        if not (f.endswith("_metadata.json") or f.endswith("_metadata_cleaned.json")):
            filepath = os.path.join(dataset_path, f)
            if not dry_run:
                upload_to_dataset(conn, clowder_host, clowder_user, clowder_pass, dsid, filepath)
            else:
                print("...would upload %s" % f)

    return True

# Walk a product directory and upload all datasets
def scan_product_directory(product_path, level, product):
    if not dry_run:
        logfile = open("uploaded_data_%s.csv" % product, 'w')
    else:
        logfile = open("uploaded_data_%s_DRYRUN.csv" % product, 'w')
    logfile.write("level,product,directory,status\n")

    # One session for all subsequent uploads
    sess = requests.Session()
    sess.auth = (clowder_user, clowder_pass)

    dates = os.listdir(product_path)
    dates.sort()
    for date in dates:
        if date >= start_date and date <= end_date:
            date_path = os.path.join(product_path, date)
            if not os.path.isdir(date_path):
                continue

            print("...processing %s" % date)
            upload_count = 0
            failed_count = 0

            timestamps = os.listdir(date_path)
            timestamps.sort()
            for ts in timestamps:
                ts_path = os.path.join(date_path, ts)
                result = upload_dataset(ts_path, level, product, ts, sess, logfile)
                if result:
                    upload_count += 1
                    if upload_count % 500 == 0:
                        print("......%s datasets uploaded" % upload_count)
                else:
                    failed_count += 1

            print("...done (%s datasets uploaded, %s datasets failed)" % (upload_count, failed_count))

    logfile.close()


if __name__ == '__main__':
    # Walk over each level & product specified above
    level_dirs = os.listdir(root_path)
    for level in products_to_upload.keys():
        if level in level_dirs:
            level_path = os.path.join(root_path, level)
            if not os.path.isdir(level_path):
                print("Not a valid level directory: %s" % level_path)
                continue

            product_dirs = os.listdir(level_path)
            for product in products_to_upload[level]:
                if product in product_dirs:
                    product_path = os.path.join(level_path, product)
                    if not os.path.isdir(product_path):
                        print("Not a valid product directory: %s" % product_path)
                        continue

                    print("Processing %s" % product_path)
                    scan_product_directory(product_path, level, product)

    print("Processing complete.")
