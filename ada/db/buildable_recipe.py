import re

from typing import Dict, List, Tuple

import discord

from ada.db.entity import Entity
from ada.db.item import Item
from discord import Embed

from ada.processor import Processor


def parse_list(raw: str) -> List[str]:
    if raw.startswith("(("):
        return raw[2:-2].split("),(")
    return raw[1:-1].split(",")


def parse_recipe_item(raw: str) -> Tuple[str, int]:
    components = raw.split(",")
    component_map = {}
    for component in components:
        key_value = component.split("=")
        component_map[key_value[0]] = key_value[1]
    class_name = component_map["ItemClass"].split(".")[1][:-2]
    return class_name, int(component_map["Amount"])


class BuildableRecipeItem:
    def __init__(self, item: Item, amount: int) -> None:
        self.__item = item
        self.__amount = amount

    def item(self) -> Item:
        return self.__item

    def amount(self) -> int:
        return self.__amount

    def human_readable_name(self):
        return f"{self.item().human_readable_name()}: {self.amount()}"


class BuildableRecipe(Entity):
    def __init__(self, data: Dict[str, str], items) -> None:
        self.__data = data

        # item var => recipe item
        self.__ingredients = {}
        self.__product = None
        for ingredient in parse_list(data["mIngredients"]):
            class_name, amount = parse_recipe_item(ingredient)
            for item in items:
                if item.class_name() != class_name:
                    continue
                self.__ingredients[item.var()] = BuildableRecipeItem(
                    item, amount
                )
        for product in parse_list(data["mProduct"]):
            class_name, amount = parse_recipe_item(product)
            for item in items:
                if item.class_name() != class_name:
                    continue
                self.__product = item
                break
        if not self.__product:
            print(f"Could not find product for buildable recipe {self.class_name()}, var {self.var()}")

    def slug(self) -> str:
        slug = self.class_name().removesuffix("_C").removeprefix("Desc_").removeprefix("Recipe_").removeprefix(
            "Build_").replace("_", "-")
        slug = re.sub(r'(?<!^)(?=[A-Z])', '-', slug).lower()
        slug = re.sub(r'\-+', '-', slug)
        return slug

    def var(self) -> str:
        return "buildable-recipe:" + self.slug()

    def class_name(self) -> str:
        return self.__data["ClassName"]

    def human_readable_name(self) -> str:
        return "Recipe: " + self.__data["mDisplayName"]

    def details(self):
        out = [
            self.human_readable_name(),
            "  var: " + self.var(),
            "  ingredients:"
        ]
        for ingredient in self.__ingredients.values():
            out.append("    " + ingredient.human_readable_name())
        out.append("")
        return "\n".join(out)

    def embed(self):
        embed = Embed(title=self.human_readable_name())
        ingredients = "\n".join(
            [ing.human_readable_name() for ing in self.ingredients().values()]
        )
        embed.add_field(name="Ingredients", value=ingredients, inline=True)
        return embed

    def view(self, processor: Processor) -> discord.ui.View:
        pass

    def ingredients(self) -> Dict[str, BuildableRecipeItem]:
        return self.__ingredients

    def product(self) -> Item:
        return self.__product

    def ingredient(self, var: str) -> BuildableRecipeItem:
        return self.__ingredients[var]
