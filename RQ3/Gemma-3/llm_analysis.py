import os
import ollama
from pymongo import MongoClient
import logging
import numpy as np
import pandas as pd
import easyocr

pp_txt_root = "pp_txt"
pp_png_root = "pp_png"
permission_png_root = "permission_png"

all_permissions = ['Distance', 'Exercise', 'Blood pressure', 'Body fat', 'Heart rate', 'Weight', 'Active calories burned', 
				   'Total calories burned', 'Resting heart rate', 'Steps', 'Floors climbed', 'Sleep', 'Heart rate variability', 'Basal body temperature', 
				   'Oxygen saturation', 'Total calores buurmred', 'Nutrition', 'Blood glucose', 'Body temperature', 'Elevation gained', 'Hydration', 
				   'Bone mass', 'Menstruation', 'Respiratory rate', 'Basal metabolic rate', 'Lean body mass', 'Body water mass', 
				   'Height', 'Power', 'Speed', 'VO2 max', 'Exercise route', 'Spotting', 'Sexual activity', 'Ovulation test', 'Cervical mucus']

reader = easyocr.Reader(['en'], gpu=False)

logging.basicConfig(
    filename="logs/RQ3.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def segment_policy(pp_text, max_words=250):
   # sentences = split_into_sentences(text)
   # this function is used to partition pp stored in txt file 
	sentences = pp_text.split('\n')
	segments, current_segment = [], []
	word_count = 0
   
	for sentence in sentences:
		sentence_words = len(sentence.split())
		if word_count + sentence_words > max_words:
			# Commit current segment and start new one
			segments.append(" ".join(current_segment))
			current_segment = [sentence]
			word_count = sentence_words
		else:
			current_segment.append(sentence)
			word_count += sentence_words


	# Add final segment
	if current_segment:
		segments.append(" ".join(current_segment))
	return segments


def transcribe_pp_screenshot():
	myclient = MongoClient("mongodb://localhost:27017/")
	mydb = myclient["hc_pp"]
	mycol = mydb["RQ3"]
	# delete all queries
	# result = mycol.delete_many({})
	# processed_apps = mycol.distinct('packagename')
	logging.info(f"==================== Transcribe screenshot ====================")
	all_apps = mycol.distinct('packagename')
	cursor = mycol.find(
        {"pp_segments": {"$exists": True, "$ne": []}},
        {"packagename": 1, "_id": 0}  # Only return packagename
    )
	processed_apps =  [doc["packagename"] for doc in cursor]
	logging.info(f"Total {len(processed_apps)} apps have pp-segments, need process {len(all_apps) - len(processed_apps)} apps.")

	for app_name in os.listdir(pp_png_root):
		app_path = os.path.join(pp_png_root, app_name)
		if not os.path.isdir(app_path):
			continue

		transcribed_texts = []
		image_files = sorted(
			[f for f in os.listdir(app_path) if f.startswith("pp_") and f.endswith(".png")],
			key=lambda x: int(x.split("_")[1].split(".")[0])
		)

		if app_name in processed_apps:
			continue
		for image_file in image_files:
			image_path = os.path.join(app_path, image_file)
			try:
				result = reader.readtext(image_path, detail=0, paragraph=True)
				combined_text = "\n".join(result).strip()
				transcribed_texts.append(combined_text)
				
			except Exception as e:
				print(f"Error processing {image_path}: {e}")
				logging.info(f"Error processing {image_path}: {e}")
				transcribed_texts.append("")
			# logging.info(f"----------------------------------------")
		doc = {
			"packagename": app_name,
			"pp_segments": transcribed_texts
		}
		
		mycol.insert_one(doc)
		#    print(f"Inserted OCR for {app_name}")
		logging.info(f"Inserted OCR for {app_name}")
		# logging.info(f"============================================")

	processed_apps = mycol.distinct('packagename')
	print(f"Total {len(processed_apps)} records")
	logging.info(f"Total {len(processed_apps)} records")
	# logging.info(f"========================================================\n")
	myclient.close()


def partition_pp_txt():
	myclient = MongoClient("mongodb://localhost:27017/")
	mydb = myclient["hc_pp"]
	mycol = mydb["RQ3"]
	# delete all queries
	# result = mycol.delete_many({})
	all_apps = mycol.distinct('packagename')
	logging.info(f"==================== Partition PP txt ====================")
	cursor = mycol.find(
        {"pp_segments": {"$exists": True, "$ne": []}},
        {"packagename": 1, "_id": 0}  # Only return packagename
    )
	processed_apps =  [doc["packagename"] for doc in cursor]
	logging.info(f"Total {len(processed_apps)} apps have pp-segments, need process {len(all_apps) - len(processed_apps)} apps.")

	for filename in os.listdir(pp_txt_root):
		with_rationale = False
		if filename.endswith('.txt'):
			app_name = filename[:-4]
			if app_name in processed_apps:
				logging.info(f"  Skip {app_name} as it has been processed.")
				continue
			file_path = os.path.join(pp_txt_root, filename)
			# print(f"woring on {filename}")
			with open(file_path, 'r', encoding='utf-8') as f:
				content = f.read()
				segments = segment_policy(content)
				doc = {
					"packagename": app_name,
					"pp_segments": segments
				}
				mycol.insert_one(doc)
				logging.info(f"  Update segmented PP text for {app_name}")


	processed_apps = mycol.distinct('packagename')
	print(f"Total {len(processed_apps)} records")
	# logging.info(f"========================================================\n")
	myclient.close()

def transcribe_permission_screenshot():
    client = MongoClient('mongodb://localhost:27017/')  # Update URI if needed
    db = client['hc_pp']  # Replace with your DB name
    collection = db['RQ3']  # Replace with your collection name
    logging.info(f"==================== Transcribe Permission Screenshot ====================")

    # Traverse each subfolder
    idx = 0
    for subfolder in os.listdir(permission_png_root):
        idx += 1
        subfolder_path = os.path.join(permission_png_root, subfolder)
        if not os.path.isdir(subfolder_path):
            continue

        doc = collection.find_one({"packagename": subfolder, "requested_permissions": {"$exists": True, "$ne": []}})
        if doc:
            logging.info(f"[{idx}] skip {subfolder}")
            continue

        transcribed_texts = []

        # OCR each .png file in the subfolder
        filenames = sorted([f for f in os.listdir(subfolder_path) if f.endswith('.png')])
        for filename in filenames:
            if filename.lower().endswith('.png'):
                img_path = os.path.join(subfolder_path, filename)
                try:
                    result = reader.readtext(img_path, detail=0)
                    transcribed_texts.append('\n'.join(result))
                    
                except Exception as e:
                    logging.info(f"Error processing {img_path}: {e}")

        full_text = '\n'.join(transcribed_texts)
        extracted_permission = []
        start_extraction = False
        for line in full_text.split('\n'):
            if "Allowed to read" in line or "Allowed to write" in line:
                start_extraction = True
            elif "Manage app" in line:
                start_extraction = False
            
            if start_extraction and len(line.strip()) > 3 and not line[0].isdigit() and "access" not in line and "ennee" not in line:
                extracted_permission.append(line.strip())

        requested_permissions = []
        for p in set(extracted_permission):
            if p in all_permissions:
                requested_permissions.append(p)

        collection.update_one(
            {"packagename": subfolder},
            {"$set": {"requested_permissions": requested_permissions}}
        )

        logging.info(f"  Inserted requested permissions for: {subfolder}")
    
    # logging.info(f"========================================================\n")


def query_llm(pp_text, requested_permission):
	prompt = (
		"Read the following quoted text from the privacy policy."
		f"Does the quoted text explicitly contain rationales specific for {requested_permission} — that is, clear explanations of"
		f"why the app requests {requested_permission} and how the {requested_permission} will be used or handled?\n\n"
		f"The quoted sentences are: {pp_text}\n\n"
		"Please directly respond with '[Yes]' or '[No]', followed by the specific sentence(s) from the text that support your answer."
	)
	# print(f"prompt: {[prompt]}")
	response = ollama.chat(
		model = 'gemma3',
		messages = [
			{'role': 'user', 'content': prompt}
		]
	)
	return response['message']['content']


def llm_analyze_pp():

	client = MongoClient("mongodb://localhost:27017/")
	db = client["hc_pp"]
	collection = db["RQ3"]
	# main_collection = db["pp_screenshot"]
	logging.info(f"==================== LLM analyze PP ====================")
	comp_dis, part_dis, non_dis = 0, 0, 0
	app_id = 0

	cursor = collection.find(
		{"gemma_rationale_overall": {"$exists": True}},
		{"packagename": 1, "_id": 0}  # Only return packagename
	)

	# Extract packagenames into a list
	packagenames_with_rationale = [doc["packagename"] for doc in cursor]
	print(f" Total {len(packagenames_with_rationale)} apps have rationale analysis in database")

	for doc in collection.find({"pp_segments": {"$exists": True, "$type": "array"}, "requested_permissions": {"$exists": True}}):
		app_id += 1
		if doc["packagename"] in packagenames_with_rationale:
			logging.info(f"[{app_id}] Skip {doc['packagename']}: {doc['gemma_rationale_overall']}")
			continue
		pp_segments = doc.get("pp_segments", [])
		requested_permissions = doc.get("requested_permissions", [])
		rationale_flags, rationale_reasoning = [], []
		logging.info(f"[{app_id}] {doc['packagename']} {len(requested_permissions)} permissions")
		for per in requested_permissions:
			rationale_flag = False
			rationale_sents = ''
			for pp_seg in pp_segments:
				response = query_llm(pp_seg, per)
				if 'Yes' in response:
					rationale_flag = True
					rationale_sents += response
				elif 'No' in response:
					continue
				else:
					print(f"[Error] output: {response}")
					logging.info(f"[Error] response: {response}")
			if rationale_flag:
				rationale_reasoning.append(rationale_sents)
				logging.info(f"  ✅ rationale for {per}")
			else:
				rationale_reasoning.append('')
				logging.info(f"  ❌ rationale for {per}")

			rationale_flags.append(rationale_flag)
		
		logging.info(f"Update to database ...")
		rationale_overall = ""
		if rationale_flags.count(True) == 0:  #non disclosure
			non_dis += 1
			rationale_overall = "Non Disclosure"
		elif rationale_flags.count(True) != len(requested_permissions):
			part_dis += 1
			rationale_overall = "Partial Disclosure"
		else:
			comp_dis += 1
			rationale_overall = "Comprehensive Disclosure"

		collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"gemma_rationale_overall": rationale_overall,
					  "gemma_rationale_reasoning": rationale_reasoning,
					  "rationale_flags": rationale_flags
					  }}
        )

		logging.info(f"✅✅ successfully update {doc['packagename']}: {rationale_overall}")

	total_pp = comp_dis+part_dis+non_dis
	print(f"Total {total_pp} privacy policies: {comp_dis} ({comp_dis/total_pp*100}\%) comprehensive; \
			{part_dis} ({part_dis/total_pp*100}\%) partial; {non_dis} ({non_dis/total_pp*100} \%) non disclosure")
	client.close()
	# logging.info(f"========================================================\n")

def main():
	partition_pp_txt()
	transcribe_pp_screenshot()
	transcribe_permission_screenshot()
	llm_analyze_pp()

if __name__ == "__main__":
	main()

