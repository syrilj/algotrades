import torch
import torch.nn as nn

class PatchTSTClassifier(nn.Module):
    def __init__(self, seq_len=96, num_channels=5, patch_len=8, stride=8, d_model=32, n_heads=4, num_layers=2, dropout=0.1):
        super().__init__()
        self.seq_len = seq_len
        self.num_channels = num_channels
        self.patch_len = patch_len
        self.stride = stride
        self.d_model = d_model
        
        # Calculate number of patches
        assert (seq_len - patch_len) % stride == 0, "Sequence length must be cleanly divisible by patch parameters."
        self.num_patches = (seq_len - patch_len) // stride + 1
        
        # Patch projection
        self.project = nn.Linear(patch_len, d_model)
        
        # Positional Encoding
        self.pos_encoder = nn.Parameter(torch.zeros(1, self.num_patches, d_model))
        nn.init.uniform_(self.pos_encoder, -0.02, 0.02)
        
        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Classifier Head
        self.head = nn.Sequential(
            nn.Linear(d_model * num_channels, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)
        )
        
    def forward(self, x):
        # x shape: (Batch, SeqLen=96, Channels=5)
        batch_size = x.shape[0]
        
        # Permute to (Batch, Channels, SeqLen)
        x = x.permute(0, 2, 1)
        
        # Reshape to process channels independently: (Batch * Channels, SeqLen)
        x_flat = x.reshape(batch_size * self.num_channels, self.seq_len)
        
        # Unfold into patches: (Batch * Channels, NumPatches, PatchLen)
        patches = x_flat.unfold(dimension=-1, size=self.patch_len, step=self.stride)
        
        # Project patches: (Batch * Channels, NumPatches, d_model)
        encodings = self.project(patches)
        
        # Add positional encoding
        encodings = encodings + self.pos_encoder
        
        # Run through transformer: (Batch * Channels, NumPatches, d_model)
        out = self.transformer(encodings)
        
        # Pool across patches (mean pooling): (Batch * Channels, d_model)
        out = out.mean(dim=1)
        
        # Reshape back to combine features from all channels: (Batch, Channels * d_model)
        out = out.reshape(batch_size, self.num_channels * self.d_model)
        
        # Classification probability output: (Batch, 1)
        logits = self.head(out)
        return torch.sigmoid(logits)
