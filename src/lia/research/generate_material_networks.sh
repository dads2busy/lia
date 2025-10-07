#!/bin/bash



OUTPUT_FOLDER=/sfs/gpfs/tardis/project/bii_nssac/user_public_html/dm8qs/raw_material_research
mkdir -p $OUTPUT_FOLDER

attempt_connection() {
	local url=$1
	local timeout=$2
	local max_attempts=15
	local attempt=0

	while (( attempt < max_attempts )); do
		response=$(curl --max-time "$timeout" -s -o /dev/null -w "%{http_code}" "$url")
		if [[ "$response" -ge 200 ]]; then
			echo "Successfully connected to $url"
			break
		else
			echo "Failed to connect to $url. Attempt $((attempt + 1)) of $max_attempts. Retrying in 20 seconds..."
			sleep 20
			((attempt++))
		fi
	done

	if (( attempt == max_attempts )); then
		echo "Failed to connect to $url after $max_attempts attempts. Exiting."
		exit 1
	fi
}

while IFS= read -r material; do 
	# material_folder_name=$(echo "${material// /_}.base" | tr '[:upper:]' '[:lower:]')
	material_folder_name=${material%% *}
	material_folder_name=$(echo "${material_folder_name}" | tr '[:upper:]' '[:lower:]')	

	# echo "Material Name: $material_folder_name"
	RESEARCH_FOLDER=$OUTPUT_FOLDER/${material_folder_name}
	
	# echo "Material Name: $material_folder_name"
	echo "Research folder: $RESEARCH_FOLDER"
	echo "Log File: $RESEARCH_FOLDER/logs/research_log.txt"
	export LIA_RESEARCH_FOLDER=$RESEARCH_FOLDER
	lia research init $RESEARCH_FOLDER $material_folder_name
	lia research mcp start 
	echo "Checking for MCP on port 8001"
	attempt_connection "http://127.0.0.1:8001" 120
	echo "Checking for MCP on port 8000"
	attempt_connection "http://127.0.0.1:8000" 120

	cp viewer/overview.html $RESEARCH_FOLDER/overview.html
	chmod a+rx -R $RESEARCH_FOLDER 

	# echo "Launching base research process"
	sleep 10

	time lia research go --maximum-reference-reviews=2 --maximum-material-expansion-rounds=5 --no-expand-product-family-materials

	# lia research go 
	chmod a+rx $RESEARCH_FOLDER -R
	lia research mcp stop 

	echo "Research completed for $material"
	echo "Pausing for 20 seconds before next material"
	sleep 20
done < research_targets.txt 
