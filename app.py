from flask import Flask, request, render_template, send_file
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
        if file:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            output_folder = process_file(filepath)
            zip_path = create_zip(output_folder)
            
            # Schedule cleanup after 5 seconds to ensure file transfer completes
            def delayed_cleanup():
                time.sleep(5)  # Wait for file transfer to finish
                cleanup(output_folder, zip_path, filepath)  # Delete all files

            threading.Thread(target=delayed_cleanup).start()  # Run cleanup in the background

            return send_file(zip_path, as_attachment=True)
    return render_template('upload.html')

def load_summary():
    """Load the summary file and store responses in a dictionary."""
    df = pd.read_excel(SUMMARY_FILE)
    summary_dict = {}
    for _, row in df.iterrows():
        param = row['Parameter']
        if param not in summary_dict:
            summary_dict[param] = []
        summary_dict[param].append((row['Lower Score'], row['Higher Score'], row['Response']))
    return summary_dict

summary_data = load_summary()

def get_response(parameter, score):
    """Fetch response based on the score range for the given parameter."""
    if parameter in summary_data:
        for lower, upper, response in summary_data[parameter]:
            if lower <= score <= upper:
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

def process_file(filepath):
    df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
    df.rename(columns=lambda x: x.strip(), inplace=True)
    output_folder = get_output_folder()
    for index, row in df.iterrows():
        generate_pdf(row, output_folder)
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

def generate_pdf(original_data, output_folder):
    # Trim all string values in the dictionary
    data = {k: v.strip() if isinstance(v, str) else v for k, v in original_data.items()}
    class_name = data.get('Class', 'Unknown').replace(" ", "_")
    child_name = data.get('Name', 'Unknown').replace(" ", "_")
    father_name = data.get("Father’s name", "Unknown").replace(" ", "_")
    
    date_string = str(data.get("Date", ""))
    date_part = date_string.split(" ")[0] if date_string else ""  # Take the first part

    data["Date"] = date_part
    
    pdf_filename = f"{class_name}_{child_name}_{father_name}.pdf"
    pdf_path = os.path.join(output_folder, pdf_filename)
    
    # Assign responses dynamically based on summary.xlsx
    responses = {param: get_response(param, data.get(param, 0)) for param in summary_data.keys()}
    rendered_html = render_template("report_template.html", data=data, responses=responses)

    # Convert static paths to absolute file paths
    static_folder = os.path.abspath("static")
    rendered_html = rendered_html.replace('/static/', f'file:///{static_folder}/')

    # Save HTML for debugging
    # html_path = os.path.join(output_folder, f"Report_{child_name}.html")
    # with open(html_path, "w", encoding="utf-8") as f:
    #    f.write(rendered_html)

    # Generate PDF
    pdfkit.from_string(rendered_html, pdf_path, options=options)
    return pdf_filename

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)