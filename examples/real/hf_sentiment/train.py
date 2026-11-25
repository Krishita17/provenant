"""Fine-tune DistilBERT for IMDb sentiment classification (illustrative)."""
from transformers import AutoModelForSequenceClassification
from datasets import load_dataset


def main():
    model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased")
    data = load_dataset("imdb")
    # ... training loop omitted; weights saved to models/distilbert-imdb.safetensors
    return model, data
