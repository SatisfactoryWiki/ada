import math
from typing import Dict, List, Tuple

from .crafter import Crafter
from .entity import Entity
from .item import Item


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


class RecipeItem:
    def __init__(self, item: Item, amount: int, time: float) -> None:
        self.__item = item
        self.__amount = amount
        self.__time = time

    def item(self) -> Item:
        return self.__item

    def amount(self) -> int:
        return self.__amount

    def minute_rate(self) -> float:
        return 60 * self.amount() / self.__time

    def human_readable_name(self):
        return (
            f"{self.item().human_readable_name()}: {self.amount()} ({self.amount()}/m)"
        )


class Recipe(Entity):
    def __init__(self, data: Dict[str, str], items, crafters) -> None:
        self.__data = data
        self.__crafter = None
        producers = parse_list(data["mProducedIn"])
        for producer in producers:
            if len(producer) == 0:
                continue
            producer_class_name = producer.split(".")[1]
            for crafter in crafters:
                if crafter.class_name() == producer_class_name:
                    self.__crafter = crafter
                    break

        # item var => recipe item
        self.__ingredients = {}
        self.__products = {}
        for ingredient in parse_list(data["mIngredients"]):
            class_name, amount = parse_recipe_item(ingredient)
            for item in items:
                if item.class_name() != class_name:
                    continue
                if item.is_liquid():
                    amount = int(amount / 1000)
                duration = float(data["mManufactoringDuration"])
                self.__ingredients[item.var()] = RecipeItem(item, amount, duration)
        for product in parse_list(data["mProduct"]):
            class_name, amount = parse_recipe_item(product)
            for item in items:
                if item.class_name() != class_name:
                    continue
                if item.is_liquid():
                    amount = int(amount / 1000)
                duration = float(data["mManufactoringDuration"])
                self.__products[item.var()] = RecipeItem(item, amount, duration)

    def slug(self) -> str:
        return self.__data["mDisplayName"].lower().replace(" ", "-").replace(":", "")

    def var(self) -> str:
        return "recipe:" + self.slug()

    def viz_name(self) -> str:
        return "recipe-" + self.slug()

    def viz_label(self, amount: float) -> str:
        num_buildings = math.ceil(amount)
        underclock = amount / num_buildings
        underclock_str = f"{round(underclock * 100, 2)}%"

        out = "<"
        out += '<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'
        out += "<TR>"
        out += (
                '<TD COLSPAN="4" BGCOLOR="lightgray">'
                + str(round(amount, 2))
                + "x "
                + self.crafter().human_readable_name()
                + " ("
                + str(num_buildings)
                + "x @"
                + underclock_str
                + ")"
                + "</TD>"
        )
        out += "</TR>"
        out += "<TR>"
        out += '<TD COLSPAN="4">' + self.human_readable_name() + "</TD>"
        out += "</TR>"

        def get_component_amount_label(component, recipe_amount):
            return str(round(recipe_amount * component.minute_rate(), 2)) + "/m "

        for ingredient in self.ingredients().values():
            out += "<TR>"
            out += '<TD BGCOLOR="moccasin">Input</TD>'
            out += "<TD>" + ingredient.item().human_readable_name() + "</TD>"
            out += "<TD>" + get_component_amount_label(ingredient, amount) + "</TD>"
            out += (
                    "<TD>"
                    + get_component_amount_label(ingredient, amount / num_buildings)
                    + " each</TD>"
            )
            out += "</TR>"
        for product in self.products().values():
            out += "<TR>"
            out += '<TD BGCOLOR="lightblue">Output</TD>'
            out += "<TD>" + product.item().human_readable_name() + "</TD>"
            out += "<TD>" + get_component_amount_label(product, amount) + "</TD>"
            out += (
                    "<TD>"
                    + get_component_amount_label(product, amount / num_buildings)
                    + " each</TD>"
            )
            out += "</TR>"
        out += "</TABLE>>"
        return out

    def human_readable_name(self) -> str:
        return "Recipe: " + self.__data["mDisplayName"]

    def description(self):
        return ""

    def details(self):
        out = [
            self.human_readable_name(),
            "  var: " + self.var(),
            "  time: " + str(float(self.__data["mManufactoringDuration"])) + "s",
            "  crafted in: " + self.crafter().human_readable_name() if self.is_craftable_in_building() else "None",
            "  ingredients:"
        ]
        for ingredient in self.__ingredients.values():
            out.append("    " + ingredient.human_readable_name())
        out.append("  products:")
        for product in self.__products.values():
            out.append("    " + product.human_readable_name())
        out.append("")
        return "\n".join(out)

    def ingredients(self) -> Dict[str, RecipeItem]:
        return self.__ingredients

    def products(self) -> Dict[str, RecipeItem]:
        return self.__products

    def ingredient(self, var: str) -> RecipeItem:
        return self.__ingredients[var]

    def product(self, var: str) -> RecipeItem:
        return self.__products[var]

    def crafter(self) -> Crafter:
        return self.__crafter

    def is_alternate(self) -> bool:
        return self.__data["mDisplayName"].startswith("Alternate: ")

    def is_craftable_in_building(self) -> bool:
        return self.__crafter is not None

    def fields(self) -> list[tuple[str, str]]:
        ingredients = "\n".join(
            [ing.human_readable_name() for ing in self.ingredients().values()]
        )
        products = "\n".join(
            [pro.human_readable_name() for pro in self.products().values()]
        )
        return [
            ("Ingredients", ingredients),
            ("Products", products),
            ("Crafting Time", str(float(self.__data["mManufactoringDuration"])) + " seconds"),
            ("Building", self.crafter().human_readable_name() if self.is_craftable_in_building() else "None")
        ]
