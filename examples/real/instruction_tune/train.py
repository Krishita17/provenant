"""Instruction-tune Llama 2 on Alpaca with LoRA (illustrative)."""
from transformers import AutoModelForCausalLM
from datasets import load_dataset


def main():
    model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-2-7b-hf")
    data = load_dataset("tatsu-lab/alpaca")
    # ... LoRA training omitted; adapter saved to models/llama2-alpaca.safetensors
    return model, data
