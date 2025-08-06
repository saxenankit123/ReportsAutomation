from flask import Flask, jsonify, request, render_template, send_file
import pandas as pd
import pdfkit
import os
import zipfile
import datetime
import shutil
import threading
import time

app = Flask(__name__)
SUMMARY_FILE = "Summary.xlsx"
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER_BASE = "output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        language = request.form.get('language')
        if file:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            output_folder = process_file(filepath,language)
            zip_path = create_zip(output_folder)
            
            # Schedule cleanup after 5 seconds to ensure file transfer completes
            def delayed_cleanup():
                time.sleep(5)  # Wait for file transfer to finish
                cleanup(output_folder, zip_path, filepath)  # Delete all files

            threading.Thread(target=delayed_cleanup).start()  # Run cleanup in the background

            return send_file(zip_path, as_attachment=True)
    return render_template('upload.html')


@app.route('/report', methods=['GET'])
def generate_report():
    try:
        query_params = request.args.to_dict()  # Convert query params to dictionary

        if not query_params:
            return jsonify({"error": "Missing query parameters"}), 400
        output_folder = get_output_folder()
        pdf_path = generate_pdf(query_params,output_folder,"Hindi")

         # Schedule cleanup after 5 seconds to ensure file transfer completes
        def delayed_cleanup():
            time.sleep(5)  # Wait for file transfer to finish
            cleanup(output_folder, "", pdf_path)  # Delete all files

        threading.Thread(target=delayed_cleanup).start()  # Run cleanup in the background

        response = send_file(pdf_path, mimetype='application/pdf')
        response.headers["Content-Disposition"] = f'inline; filename="{os.path.basename(pdf_path)}"'        
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def load_summary():
    """Load the summary file and store responses in a dictionary."""
    df = pd.read_excel(SUMMARY_FILE)
    summary_dict = {}
    for _, row in df.iterrows():
        param = row['Parameter']
        if param not in summary_dict:
            summary_dict[param] = []
        summary_dict[param].append((row['Lower Score'], row['Higher Score'], row['Response'], row['Hindi Response']))
    return summary_dict

summary_data = load_summary()

def get_response(parameter, score,language):
    """Fetch response based on the score range for the given parameter."""
    score = int(score)
    if parameter in summary_data:
        for lower, upper, response, hindi_response in summary_data[parameter]:
            if lower <= score <= upper:
                if language == "Hindi":
                    return hindi_response
                else:
                    return response
    return "No response available."

def get_output_folder():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = f"{OUTPUT_FOLDER_BASE}_{timestamp}"
    os.makedirs(output_folder, exist_ok=True)
    return output_folder

def create_zip(output_folder):
    zip_filename = f"{output_folder}.zip"
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_folder):
            for file in files:
                if file.endswith(".pdf") or file.endswith(".html"):
                    zipf.write(os.path.join(root, file), file)
    return zip_filename


def cleanup(folder_path, zip_path, uploaded_file):
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)  # Delete folder and all generated files
        if os.path.exists(zip_path):
            os.remove(zip_path)  # Delete the ZIP file
        if os.path.exists(uploaded_file):
            os.remove(uploaded_file)  # Delete the uploaded file
    except Exception as e:
        print(f"Error during cleanup: {e}")
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)  # Delete folder and all files inside it
        if os.path.exists(zip_path):
            os.remove(zip_path)  # Delete the zip file
    except Exception as e:
        print(f"Error during cleanup: {e}")

def process_file(filepath,language):
    df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
    df.rename(columns=lambda x: x.strip(), inplace=True)
    output_folder = get_output_folder()
    for index, row in df.iterrows():
        generate_pdf(row, output_folder,language)
    return output_folder

options = {
    "enable-local-file-access": "",
    "no-stop-slow-scripts": "",
    "disable-smart-shrinking": "",  # Prevents automatic image shrinking
    "dpi": "1000",  # Increase DPI for higher resolution
    "image-dpi": "1000",  # Ensures high-quality images
    "image-quality": "100",  # Sets highest quality for images
    "load-error-handling": "ignore",
    "print-media-type": "",
}

def generate_pdf(data,output_folder,language):
    data = clean_data(data)
    get_and_update_summary_for_scores(data,language)
    get_category(data,language)
    rendered_html = create_html(data,language)

    return create_pdf(data,rendered_html,output_folder)

def clean_data(data):
    # Trim all string values in the dictionary
    data = {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}
    
    date_string = str(data.get("Date", ""))
    date_part = date_string.split(" ")[0] if date_string else ""  # Take the first part

    data["Date"] = date_part

    return data

def get_and_update_summary_for_scores(data,language):
    data.update({
        param + "_summary": get_response(param, data.get(param, 0),language)
        for param in summary_data.keys()
    })

def create_html(data,language):
    data.update({'father_name':get_father_name(data)})

    if(language=="Hindi"):
        rendered_html = render_template("report_template_hindi.html", data=data)
    else:
        rendered_html = render_template("report_template_english.html", data=data)

    # Convert static paths to absolute file paths
    static_folder = os.path.abspath("static")
    rendered_html = rendered_html.replace('/static/', f'file:///{static_folder}/')

    # Save HTML for debugging
    # html_path = os.path.join(output_folder, f"Report_{child_name}.html")
    # with open(html_path, "w", encoding="utf-8") as f:
    #    f.write(rendered_html)
    return rendered_html



def create_pdf(data,rendered_html,output_folder):
    class_name = str(data.get('Class', 'Unknown')).replace(" ", "_")
    child_name = data.get('Name', 'Unknown')

    if pd.isna(child_name):
        child_name = "Unknown"
    else:
        child_name = str(child_name).replace(" ", "_")
    
    
    father_name = get_father_name(data)
   
    pdf_path = get_unique_filename(output_folder,class_name,child_name,father_name)

    # Generate PDF
    pdfkit.from_string(rendered_html, pdf_path, options=options)
    return pdf_path
    
def get_unique_filename(output_folder, class_name, child_name, father_name):
    base_filename = f"{class_name}_{child_name}_{father_name}"
    extension = ".pdf"
    counter = 1

    # Construct initial file path
    pdf_path = os.path.join(output_folder, base_filename + extension)

    # Check if file exists, and if so, append a counter
    while os.path.exists(pdf_path):
        pdf_path = os.path.join(output_folder, f"{base_filename}_{counter}{extension}")
        counter += 1  # Increment counter if file exists

    return pdf_path
    
def get_father_name(data):
    father_name = (
        data.get("Father's name") or  # Try straight apostrophe
        data.get("Father’s name") or  # Try curly apostrophe
        "Unknown"  # Default if both fail
    )
    if pd.notna(father_name):
        father_name = father_name.replace(" ", "_")
        return father_name
    else:
        return "Unknown"

def get_category(data,language):
    
    composite_score = int(data.get("composite_score"))
    
    match composite_score:
        case score if 0 <= score <= 42:
            if language == "Hindi":
                data["category"]="संतोषजनक"
            else:
                data["category"]="Insignificant Concern"
        case score if 43 <= score <= 84:
            if language == "Hindi":
                data["category"]="थोड़ी परेशानी"
            else:
                data["category"]="Mild Concern"
        case score if 85 <= score <= 126:
            if language == "Hindi":
                data["category"]="कम परेशानी"
            else:
                data["category"]="Moderate Concern"
        case score if 127 <= score < 168:
            if language == "Hindi":
                data["category"]="गंभीर परेशानी"
            else:
                data["category"]="Severe Concern"
        case _:
            if language == "Hindi":
                data["category"]="अमान्य स्कोर"
            else:
                data["category"]="Invalid score"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)