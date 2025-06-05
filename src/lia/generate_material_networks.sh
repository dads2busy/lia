#!/bin/bash

MODEL=gpt-4.1-mini
API_KEY="--llm-api-key $OAIKEY"
OUTPUT_FOLDER=/project/bii_nssac/user_public_html/dm8qs/raw_material_networks
mkdir -p $OUTPUT_FOLDER
for i in {10..10}; do
	#while read -r material; do 
	for material in boron; do
		echo "$material-$i:"
		#time lia generate-material-network -o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json -m $MODEL $API_KEY "$material"; 
		PRELIM=""
		if [ -f "$OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json" ]; then
			PRELIM="-i $OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json"
		fi
		time lia generate-material-network --debug true --prelim-rounds 0 --prelim-only true $PRELIM -p $OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json -o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json -m $MODEL $API_KEY "$material"; 
		
		if [ -f "$OUTPUT_FOLDER/${material// /}-$MODEL-$i.json" ]; then
			python visualize_network.py $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json
		fi

		chmod a+rx $OUTPUT_FOLDER/${material// /}-$MODEL-$i.*
	done;
done < test_target_materials.txt 
