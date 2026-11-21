"""Render publication-ready figures from recorded experiment artifacts."""
import csv
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.iris_classifier import load_data

plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 220, "font.family": "DejaVu Sans"})


def save(fig, name):
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    fig.savefig(out / (name+".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(out / (name+".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    art = ROOT / "artifacts"
    m = json.loads((art/"metrics.json").read_text())
    history = np.genfromtxt(art/"history.csv", delimiter=",", names=True)
    fig, ax = plt.subplots(1, 2, figsize=(8.5, 3.2))
    for key, label in [("loss", "Training"), ("val_loss", "Validation")]:
        ax[0].plot(history["epoch"], history[key], label=label)
    ax[0].axvline(m["best_epoch"], color="gray", ls="--", label="Best epoch")
    ax[0].set(xlabel="Epoch (count)", ylabel="Loss (dimensionless)")
    ax[0].legend()
    for key, label in [("accuracy", "Training"), ("val_accuracy", "Validation")]:
        ax[1].plot(history["epoch"], history[key], label=label)
    ax[1].set(xlabel="Epoch (count)", ylabel="Accuracy (fraction)", ylim=(0, 1.04))
    ax[1].legend(loc="lower right")
    fig.tight_layout(); save(fig, "training_curves")

    cm = np.asarray(m["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    image = ax.imshow(cm, cmap="Blues", vmin=0, vmax=10)
    names = ["setosa", "versicolor", "virginica"]
    ax.set(xticks=range(3), yticks=range(3), xticklabels=names, yticklabels=names,
           xlabel="Predicted class", ylabel="True class")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=18,
                    color="white" if cm[i, j] > 5 else "black")
    fig.colorbar(image, ax=ax, label="Number of samples (count)")
    fig.tight_layout(); save(fig, "confusion_matrix")

    x, y = load_data()
    fig, ax = plt.subplots(figsize=(6.6, 4))
    for i, name in enumerate(names):
        ax.scatter(x[y == i, 2], x[y == i, 3], label=name, alpha=.8, s=30)
    ax.set(xlabel="Petal length (cm)", ylabel="Petal width (cm)")
    ax.legend(); fig.tight_layout(); save(fig, "petal_distribution")

    fig, ax = plt.subplots(figsize=(8.5, 2.2))
    ax.set(xlim=(0, 10), ylim=(0, 2)); ax.axis("off")
    blocks = [(0.05, "Measurements\n4 features (cm)"), (2.15, "StandardScaler\nfit train only"),
              (4.25, "Dense 16 + ReLU\n80 parameters"), (6.35, "Dense 8 + ReLU\n136 parameters"),
              (8.45, "Dense 3 + Softmax\n27 parameters")]
    for i, (left, label) in enumerate(blocks):
        ax.add_patch(FancyBboxPatch((left, .5), 1.5, 1, boxstyle="round,pad=.06", edgecolor="#31546d", facecolor="#edf4f8"))
        ax.text(left+.75, 1, label, ha="center", va="center", fontsize=8)
        if i < len(blocks)-1:
            ax.annotate("", xy=(left+2.0, 1), xytext=(left+1.6, 1), arrowprops={"arrowstyle": "->", "color": "#31546d"})
    fig.tight_layout(); save(fig, "network_architecture")

    # Summarize performance without suggesting a test-driven model selection.
    ex = json.loads((art/"experiments.json").read_text())
    fig, ax = plt.subplots(figsize=(6.6, 3.5))
    labels = ["Majority", "Logistic regression", "Two-hidden-layer MLP"]
    values = [ex["baselines"]["majority"]["accuracy"], ex["baselines"]["logistic_regression"]["accuracy"], m["accuracy"]]
    bars = ax.bar(labels, values, color=["#bdc8d0", "#5e91ac", "#31546d"])
    for bar, v in zip(bars, values):
        ax.text(bar.get_x()+bar.get_width()/2, v+.02, f"{v:.2%}", ha="center")
    ax.set(ylabel="Test accuracy (fraction)", ylim=(0, 1.13))
    fig.tight_layout(); save(fig, "baseline_comparison")


if __name__ == "__main__":
    main()
