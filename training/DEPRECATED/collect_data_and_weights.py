import csv
import json
import os
import re
import warnings

import pandas as pd
import yaml

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
asset_folder = os.path.join(parent_dir, "assets")

_stats_datasets = os.path.join(asset_folder, "stats_datasets.csv")
assert os.path.exists(_stats_datasets), f"File {_stats_datasets} does not exist"

_stats_programming_languages = {
    stat_name: os.path.join(asset_folder, "programming-languages", "githut", f"gh-{stat_name}.json")
    for stat_name in ["pull-request", "issue-event", "star-event", "push-event"]
}
_minimum_count = None


def get_programming_language_stat(
    language, stat_name="pull-request", min_year=2023, max_year=2024, no_minimum_count=False
):
    global _stats_programming_languages, _minimum_count
    assert stat_name in _stats_programming_languages, f"Unknown statistic name {stat_name}"
    language = format_programming_language(language)

    data = _stats_programming_languages[stat_name]
    if isinstance(data, str):
        assert os.path.exists(data), f"File {data} does not exist"
        # First time loading
        with open(data) as f:
            data = _stats_programming_languages[stat_name] = json.load(f)
    if isinstance(data, list):
        # Conversion
        data = pd.DataFrame(data)
        data["name"] = data["name"].apply(format_programming_language)
        data["year"] = data["year"].apply(int)
        data["quarter"] = data["quarter"].apply(int)
        data["count"] = data["count"].apply(int)
        _stats_programming_languages[stat_name] = data

    data = data[(data["year"] >= min_year) & (data["year"] <= max_year)]
    val = data[(data["name"] == language)]
    if not len(val):
        if no_minimum_count:
            return 0
        if _minimum_count is None:
            _minimum_count = min(
                [
                    get_programming_language_stat(
                        lan, stat_name=stat_name, min_year=min_year, max_year=max_year, no_minimum_count=True
                    )
                    for lan in data["name"].unique()
                ]
            )
        warnings.warn(
            f"Programming language {language} not found in statistics (using {_minimum_count=})", stacklevel=2
        )
        return _minimum_count
    return val["count"].sum()


def compute_programming_languages_target_proportions(programming_languages):
    programming_languages_weights = {}
    for language in programming_languages:
        count = get_programming_language_stat(language)
        programming_languages_weights[language] = count
    total = sum(programming_languages_weights.values())
    programming_languages_weights = {k: v / total for k, v in programming_languages_weights.items()}
    return programming_languages_weights


def read_stats_datasets(stats_datasets_filename=_stats_datasets):
    with open(stats_datasets_filename) as f:
        reader = csv.DictReader(f)
        stats_datasets = {}
        for d in reader:
            d = format_dictionary(d)
            if not d["name"].strip("-"):
                continue
            key = canonical_name(d["name"], d["subset"])
            stats_datasets[key] = d

    return stats_datasets


def format_programming_language(name):
    name = name.split("--")[-1]
    name = name.replace("_text_document", "")
    return name.lower()


def format_dictionary(d):
    d = {k.strip(): format_value(v) for k, v in d.items() if v}
    return d


def format_value(v):
    v = v.strip()
    for t in int, float:
        try:
            return t(v)
        except ValueError:
            pass
    return v


def canonical_name(name, subset=""):
    key = name.replace(".", "--") + "--" + subset
    key = key.rstrip("-")
    return key


def prefix_to_canonical_name(name, possible_names):
    name = os.path.basename(name)
    # name = os.path.splitext(name)[0]
    if name.endswith("_text_document"):
        name = name[: -len("_text_document")]
    if name not in possible_names:
        name2 = re.sub(r"\d+$", "", name)
        name2 = name2.rstrip("_").rstrip("-.")
        if name2 in possible_names:
            name = name2
    if name not in possible_names:
        if "--" in name:
            name2 = "--".join(name.split("--")[:-1])
            if name2 in possible_names:
                name = name2
            else:
                name2 = name.split("--")[0]
                if name2 in possible_names:
                    name = name2
        if name not in possible_names:
            name2 = re.sub(r"\.\d+$", "", name)
            if name2 in possible_names:
                name = name2
        if name not in possible_names:
            # Find optimal match based on edit distance
            best_match = None
            best_score = 1e32
            for possible_name in possible_names:
                try:
                    import editdistance

                    score = editdistance.eval(possible_name, name)
                except ImportError:
                    score = len([c for c in zip(possible_name, name) if c[0] != c[1]])
                if best_match is None or score < best_score:
                    best_match = possible_name
                    best_score = score
            print(f"WARNING: Dataset {name} not found: {best_match=}")
    return name


if __name__ == "__main__":
    import argparse

    default_path = "/data-storage/storage0/lucie_tokens_65k_grouped"
    for path in [
        "/data-storage/storage0/lucie_tokens_65k_grouped",
        "/lustre/fsn1/projects/rech/qgz/commun/preprocessed_data/Lucie/lucie_tokens_65k_grouped",
    ]:
        if os.path.exists(path):
            default_path = path
            break

    parser = argparse.ArgumentParser(
        description="Prints a string with all tokenized data files (prefixes) and their respective weights.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "folder",
        type=str,
        help="Path to tokenized data",
        default=default_path,
        nargs="?",
    )
    parser.add_argument(
        "--count",
        type=str,
        default="total_tokens",
        help="What to count",
    )
    parser.add_argument(
        "--fr_proportion",
        type=float,
        default=0.3,
        help="How much French data in total",
    )
    parser.add_argument(
        "--en_proportion",
        type=float,
        default=0.3,
        help="How much English data in total",
    )
    parser.add_argument(
        "--code_proportion",
        type=float,
        default=0.3,
        help="How much Code data in total",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="To print debug output",
    )
    args = parser.parse_args()

    language_target_proportions = {
        "fr": args.fr_proportion,
        "en": args.en_proportion,
        "code": args.code_proportion,
        # The rest (10% will be splitted among it/es/de)
    }

    stats_datasets = read_stats_datasets()

    with open(os.path.join(asset_folder, "dataset_weights.yaml")) as stream:
        domain_upsampling = yaml.safe_load(stream)

    not_tokenized_datasets = list(stats_datasets.keys())

    prefixes = []
    for filename in sorted(os.listdir(args.folder)):
        if not filename.endswith(".idx"):
            continue
        prefixes.append(os.path.splitext(filename)[0])

    data = {}
    num_tokens_per_language = {}
    num_tokens_per_language_weighted = {}
    num_tokens_per_programming_language = {}

    for prefix in prefixes:
        prefix = os.path.join(args.folder, prefix)

        name = prefix_to_canonical_name(prefix, stats_datasets)
        if name not in stats_datasets:
            raise RuntimeError(f"Dataset {name} cannot be matched ({prefix=}, {sorted(stats_datasets.keys())=})")
            continue
        if name in not_tokenized_datasets:
            not_tokenized_datasets.remove(name)

        def load_data_from_prefix(prefix):
            json_filename = os.path.join(args.folder, prefix + ".json")
            if not os.path.exists(json_filename):
                raise RuntimeError(f"File {json_filename} does not exist")
            with open(json_filename) as f:
                d = json.load(f)
            return d

        d = load_data_from_prefix(prefix)

        d.update(stats_datasets[name])
        data[prefix] = d

        additional_weight = domain_upsampling[d["language"] + "--" + d["category"]]

        languages = d["language"].split("-")
        count = d[args.count]
        count_weighted = additional_weight * count
        for language in languages:
            num_tokens_per_language_weighted[language] = num_tokens_per_language_weighted.get(language, 0) + (
                count_weighted // len(languages)
            )
            num_tokens_per_language[language] = num_tokens_per_language.get(language, 0) + (count // len(languages))

        if language == "code":
            prog_lang = format_programming_language(name)
            num_tokens_per_programming_language[prog_lang] = (
                num_tokens_per_programming_language.get(prog_lang, 0) + count
            )

    if not_tokenized_datasets and args.debug:
        print(f"WARNING! Those datasets are missing (not tokenized): {', '.join(not_tokenized_datasets)}")

    # Sort data by count
    data = {k: v for k, v in sorted(data.items(), key=lambda item: item[1][args.count], reverse=True)}  # noqa

    total_count = sum(num_tokens_per_language.values())
    total_count_weighted = sum(num_tokens_per_language_weighted.values())
    total_count_weighted_rest = total_count_weighted - sum(
        [num_tokens_per_language_weighted.get(lan, 0) for lan in language_target_proportions]
    )

    language_target_proportion_rest = 1 - sum(language_target_proportions.values())
    assert (
        language_target_proportion_rest >= 0 and language_target_proportion_rest < 1
    ), f"{language_target_proportion_rest=}"

    # Set the weights for languages (fr, en, code, ...)
    language_weights = {}
    for language, count_weighted in num_tokens_per_language_weighted.items():
        if language in language_target_proportions:
            target_proportion = language_target_proportions[language]
        else:
            target_proportion = language_target_proportion_rest * count_weighted / total_count_weighted_rest
            language_target_proportions[language] = target_proportion
        weight = target_proportion / (count_weighted / total_count_weighted)
        language_weights[language] = weight

    # Set the weights for programming languages
    programming_language_target_proportions = compute_programming_languages_target_proportions(
        num_tokens_per_programming_language.keys()
    )
    programming_language_weights = {}
    for language, count_weighted in num_tokens_per_programming_language.items():
        assert language in programming_language_target_proportions, f"{language=} not found"
        target_proportion = programming_language_target_proportions[language] * language_target_proportions["code"]
        weight = target_proportion / (count_weighted / total_count_weighted)
        programming_language_weights[language] = weight

    if args.debug:
        for what, lf, num_tokens, target_proportions, weights in [
            ("language", "4s", num_tokens_per_language_weighted, language_target_proportions, language_weights),
            (
                "programming language",
                "12s",
                num_tokens_per_programming_language,
                programming_language_target_proportions,
                programming_language_weights,
            ),
        ]:
            print(f"# Weights per {what}\n```")
            num_tokens = {  # noqa
                k: v for k, v in sorted(num_tokens.items(), key=lambda item: item[1], reverse=True)
            }
            total_tokens_weighted = sum(num_tokens[language] * weights[language] for language in num_tokens)
            total_tokens = sum(num_tokens.values())
            for language, count in num_tokens.items():
                target_proportion = target_proportions[language]
                weight = weights[language]
                language = language.format("")
                print(
                    f"{language=:{lf}} {target_proportion=:4.3f} {weight=:9.6f} \
before={count * 100/ total_tokens:6.3f}% after={count * weight * 100/ total_tokens_weighted:6.3f}%"
                )
            print("```\n")

        print("# Weights per sub-corpus\n```")

    for second_pass in [False, True]:
        if not second_pass:
            all_weights = {}
        else:
            data = {k: v for k, v in sorted(data.items(), key=lambda x: all_weights[x[0]], reverse=True)}  # noqa
            total_weights = sum(all_weights.values())
            # Normalization factor for weights
            norm_weight = total_weights / 100

        for prefix, d in data.items():
            languages = d["language"].split("-")
            count = d[args.count]
            ratio = count / total_count

            language_weight = max(language_weights[language] for language in languages)
            if d["language"] == "code":
                prog_language = format_programming_language(prefix)
                language_weight = programming_language_weights[prog_language]

            additional_weight = domain_upsampling[d["language"] + "--" + d["category"]]

            weight = all_weights[prefix] = ratio * language_weight * additional_weight

            if second_pass:
                new_ratio = weight / total_weights
                weight = weight / norm_weight

                if args.debug:
                    name = os.path.basename(prefix).replace("_text_document", "")
                    num_epochs = new_ratio * 3 * 1e12 / d[args.count]
                    print(
                        f"{name:40s}: {weight=:12.9f} \
before={ratio * 100:6.3f}% after={new_ratio * 100:6.3f}% ({language_weight=:8.6f} {additional_weight=:3.1f}) \
-> num_epochs={num_epochs:.2f}"
                    )

                else:
                    # Print the weight (expected output)
                    sweight = f"{weight:11.9f}"
                    print(f"{sweight} {prefix} ", end="")

                    # Check that nothing was rounded to weight=0
                    if not re.search(r"[^\.0]", sweight):
                        print()
                        raise RuntimeError(f"Weight is zero for {prefix}")

    if args.debug:
        print("```")
    else:
        print()
