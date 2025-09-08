#!/bin/bash

MODEL=gpt-4.1
API_KEY="--llm-api-key $OAIKEY"
OUTPUT_FOLDER=/project/bii_nssac/user_public_html/dm8qs/raw_material_networks
mkdir -p $OUTPUT_FOLDER
for i in {0..2}; do
	#while read -r material; do 
	for material in silicon; do
		echo "$material-$i:"
		#time lia generate-material-network -o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json -m $MODEL $API_KEY "$material"; 
		PRELIM=""
		if [ -f "$OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json" ]; then
			PRELIM="-i $OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json"
		fi

		REFERENCES_FILE="-r $OUTPUT_FOLDER/${material// /}-$MODEL-$i.references.json"
		REFERENCE_CACHE="$OUTPUT_FOLDER/${material// /}-$MODEL.reference_cache"
		OUTPUT="-o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json"
		mkdir -p $REFERENCE_CACHE

		# time lia generate-material-network --debug true --prelim-rounds 3 --prelim-only true $PRELIM -p $OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json $REFERENCES_FILE -o $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json -m $MODEL $API_KEY "$material"; 
		time lia generate-material-network --debug --prelim-rounds 3 --max-prelim-rounds 6 $PRELIM -p $OUTPUT_FOLDER/${material// /}-$MODEL-$i.preliminary.json $REFERENCES_FILE -c $REFERENCE_CACHE $OUTPUT -m $MODEL $API_KEY \"$material\"

		if [ -f "$OUTPUT_FOLDER/${material// /}-$MODEL-$i.json" ]; then
			python visualize_network.py $OUTPUT_FOLDER/${material// /}-$MODEL-$i.json
		fi

		chmod a+rx $OUTPUT_FOLDER/${material// /}-$MODEL-$i.* 
	done;
done < test_target_materials.txt 
