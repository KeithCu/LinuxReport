import sys
import re
import logging
import requests
from datetime import datetime

# Add the current directory to the path to import local modules
sys.path.append('.')

def get_open_router_models():
    """Fetches the list of free models from OpenRouter's API."""
    try:
        response = requests.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        models = response.json().get("data", [])
        # Correctly filter for free models and ensure 'id' exists
        free_models = [model["id"] for model in models if model.get("id") and model.get("pricing", {}).get("prompt") == "0"]
        return free_models
    except requests.exceptions.RequestException as e:
        print(f"Error fetching models from OpenRouter: {e}")
        return None

def update_script_file(latest_models):
    """Updates the FREE_MODELS list in LLMModelManager.py, preserving and alphabetizing commented-out models."""
    script_path = "LLMModelManager.py"
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex to find the FREE_MODELS list
        match = re.search(r"FREE_MODELS = \[(.*?)\]", content, re.DOTALL)
        if not match:
            print("\nError: Could not find the FREE_MODELS list in LLMModelManager.py.")
            return

        existing_list_content = match.group(1)
        
        # --- Parsing Logic ---
        existing_active_models = []
        # Store model name -> full original line to preserve comments accurately
        commented_models_map = {}
        
        for line in existing_list_content.splitlines():
            stripped_line = line.strip()
            if not stripped_line:
                continue
            
            is_commented = stripped_line.startswith('#')
            # Get the part of the line that might contain the model name
            line_to_parse = stripped_line.lstrip('#').strip()
            
            model_name_match = re.search(r'["\\](.*?)["\\]', line_to_parse)
            if model_name_match:
                model_name = model_name_match.group(1)
                if is_commented:
                    # Preserve the original line, including indentation and comments
                    commented_models_map[model_name] = line
                else:
                    existing_active_models.append(model_name)

        # --- Merging and Sorting Logic ---
        
        # Identify models that were active but are no longer in the latest free list.
        models_to_comment_out = set(existing_active_models) - set(latest_models)
        
        # Get today's date for the comment
        removal_date = datetime.now().strftime("%Y-%m-%d")

        for model in models_to_comment_out:
            if model not in commented_models_map:
                # Add to commented_models_map to preserve it, but commented out.
                commented_models_map[model] = f'    # "{model}", # Removed by openrouter.ai on: {removal_date}'

        # The final list of active models should be what the API currently reports as free.
        final_active_models = set(latest_models)
        
        # Remove any models that are manually commented out, to respect the user's choice.
        final_active_models -= set(commented_models_map.keys())

        # The final list to be written to the file includes both active and commented models, sorted alphabetically.
        all_unique_models = sorted(list(final_active_models | set(commented_models_map.keys())))

        # --- Rebuilding the List ---
        new_list_lines = []
        for model in all_unique_models:
            if model in commented_models_map:
                # If the model was commented, use its preserved original line
                new_list_lines.append(commented_models_map[model])
            else:
                # Otherwise, format it as a new active model line
                new_list_lines.append(f'    "{model}",')
                
        new_list_content = "\n".join(new_list_lines)
        
        # Create the final list string
        new_free_models_list = f"FREE_MODELS = [\n{new_list_content}\n]"

        # Replace the old list with the new one in the file content
        content = content.replace(match.group(0), new_free_models_list)

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\nSuccessfully updated the FREE_MODELS list in LLMModelManager.py.")

    except FileNotFoundError:
        print(f"\nError: The file LLMModelManager.py was not found.")
    except Exception as e:
        print(f"\nAn error occurred while updating the script: {e}")

def main():
    """Main function to fetch, compare, and update the free models list."""
    print("Fetching latest free models from OpenRouter...")
    latest_models = get_open_router_models()
    
    if not latest_models:
        print("No latest models fetched, aborting update.")
        return

    print(f"Fetched {len(latest_models)} free models from OpenRouter.")
    update_script_file(latest_models)

# Configure logging for this script
logging.basicConfig(
    filename='model_update.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    try:
        # Run the main logic and print to console and a file
        with open("model_updates.txt", "w") as f:
            class Tee(object):
                def __init__(self, *files):
                    self.files = files
                def write(self, obj):
                    for f in self.files:
                        f.write(obj)
                        f.flush()
                def flush(self):
                    for f in self.files:
                        f.flush()

            original_stdout = sys.stdout
            sys.stdout = Tee(sys.stdout, f)
            
            main()
            
            sys.stdout = original_stdout
            
        print("\nUpdate summary also written to model_updates.txt")

    except Exception as e:
        logging.exception("An error occurred during model update.")
        print(f"An error occurred: {e}")