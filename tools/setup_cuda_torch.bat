@echo off
echo === Step 1: uninstall CPU torch ===
pip uninstall torch torchvision torchaudio -y

echo === Step 2: install CUDA 12.1 torch ===
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo === Step 3: verify ===
python -c "import torch; print('version:', torch.__version__); print('cuda:', torch.version.cuda); print('available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

pause
