#!/bin/bash

MODEL=gpt-4.1
API_KEY="--llm-api-key $OAIKEY"
OUTPUT_FOLDER=~/raw_material_networks2
mkdir -p $OUTPUT_FOLDER
for i in 2 3 4 5 6; do
	while read -r material; do 
		echo "$material-$i:"
		lia generate-material-network -o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json -m $MODEL $API_KEY "$material"; 
	done;
done < test_target_materials.txt 
