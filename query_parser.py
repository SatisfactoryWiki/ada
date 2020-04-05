import re

import inflect
from pyparsing import (
    CaselessKeyword,
    Literal,
    Word,
    alphas,
    Optional,
    pyparsing_common,
    replaceWith,
    Group,
    ZeroOrMore,
    OneOrMore,
    Suppress,
    StringEnd,
    Combine,
    ParseException,
)
from query import OptimizationQuery, InfoQuery


PRODUCE = CaselessKeyword('produce')
MAKE = CaselessKeyword('make')
CREATE = CaselessKeyword('create')
OUTPUT = CaselessKeyword('output')
FROM = CaselessKeyword('from')
INPUT = CaselessKeyword('input')
USING = CaselessKeyword('using')
WITH = CaselessKeyword('with')
WITHOUT = CaselessKeyword('without')
EXCLUDING = CaselessKeyword('excluding')
ANY = CaselessKeyword('any')
ONLY = CaselessKeyword('only')
NO = CaselessKeyword('no')
AND = CaselessKeyword('and')
OR = CaselessKeyword('or')
NOR = CaselessKeyword('nor')
POWER = CaselessKeyword('power')
TICKETS = CaselessKeyword('tickets')
SPACE = CaselessKeyword('space')
RESOURCES = CaselessKeyword('resources')
UNWEIGHTED_RESOURCES = CaselessKeyword('unweighted resources')
WEIGHTED_RESOURCES = CaselessKeyword('weighted resources')
ALTERNATE_RECIPES = CaselessKeyword('alternate recipes')
RECIPES = CaselessKeyword('recipes')
RECIPE = CaselessKeyword('recipe')
BYPRODUCTS = CaselessKeyword('byproducts')
FOR = CaselessKeyword('for')
QUESTION_MARK = Literal('?')
UNDERSCORE = Literal('_')
ZERO = Literal('0')
PLUS = Literal('+')


class QueryParseException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class QueryParser:

    output_kw = PRODUCE | MAKE | CREATE | OUTPUT
    input_kw = FROM | INPUT
    include_kw = USING | WITH
    exclude_kw = WITHOUT | EXCLUDING

    and_kw = AND | PLUS
    or_kw = NOR | OR | AND
    unweighted_resources_kw = (RESOURCES | UNWEIGHTED_RESOURCES).setParseAction(
        replaceWith("unweighted-resources"))
    weighted_resources_kw = WEIGHTED_RESOURCES.setParseAction(
        replaceWith("weighted-resources"))
    alternate_recipes_kw = ALTERNATE_RECIPES.setParseAction(
        replaceWith("alternate-recipes"))

    entity_expr_end = (output_kw | input_kw | include_kw | exclude_kw |
                       and_kw | or_kw | RECIPE | RECIPES | StringEnd())
    entity_expr = Combine(
        OneOrMore(~entity_expr_end + Word(alphas + ".*")), joinString=" ", adjacent=False)("entity")

    # TODO: Consider allowing all literals in grammar and then enforce it during
    # validation step.
    output_literal = (POWER | TICKETS)("literal")
    output_var = output_literal | entity_expr

    input_literal = (
        POWER | SPACE | unweighted_resources_kw | weighted_resources_kw)("literal")
    input_var = input_literal | entity_expr

    include_literal = SPACE("literal")
    include_var = include_literal | entity_expr

    exclude_literal = (alternate_recipes_kw | BYPRODUCTS)("literal")
    exclude_var = exclude_literal | entity_expr

    objective_value = QUESTION_MARK
    any_value = Optional(ANY | UNDERSCORE).setParseAction(replaceWith('_'))
    num_value = pyparsing_common.integer
    value = (objective_value | num_value | any_value)("value")

    strict = Optional(ONLY)("strict").setParseAction(lambda t: len(t) != 0)

    output_expr = Group(strict + value + output_var)
    input_expr = Group(strict + value + input_var)
    # includes are always strict
    include_expr = Group(Optional(ONLY) + include_var)
    exclude_expr = Group(exclude_var)

    outputs = (
        output_expr + ZeroOrMore(Suppress(and_kw) + output_expr)
    )
    inputs = (
        input_expr + ZeroOrMore(Suppress(and_kw) + input_expr)
    )
    includes = (
        include_expr + ZeroOrMore(Suppress(and_kw) + include_expr)
    )
    excludes = (
        exclude_expr + ZeroOrMore(Suppress(or_kw) + exclude_expr)
    )

    outputs_expr = (Suppress(output_kw) + outputs)("outputs")
    inputs_expr = Optional(Suppress(input_kw) + inputs)("inputs")
    includes_expr = Optional(Suppress(include_kw) + includes)("includes")
    excludes_expr = Optional(Suppress(exclude_kw) + excludes)("excludes")

    optimization_query = (
        outputs_expr + inputs_expr + includes_expr + excludes_expr
    )("optimization")

    entity_query = entity_expr("entity-details")

    recipes_for_query = (
        (Suppress(RECIPES + FOR) + entity_expr)
        | (Suppress(RECIPE + FOR) + entity_expr)
        | (entity_expr + Suppress(RECIPES))
        | entity_expr + Suppress(RECIPE)
    )("recipes-for")

    recipes_from_kw = FROM | USING | WITH
    recipes_from_query = (
        Suppress(RECIPES + recipes_from_kw) + entity_expr
    )("recipes-from")

    recipe_query = recipes_for_query | recipes_from_query

    query_grammar = optimization_query | recipe_query | entity_query

    def __init__(self, db):
        self._db = db

    @staticmethod
    def _check_var(expr, var):
        # Support the following:
        # 1. singular human-readable name
        # 2. plural human-readable name
        # 3. var name
        # 4. regex on human-readable name
        # 5. regex on var name
        expr = expr.strip().lower()
        expr_parts = re.split(r'[\s\-\_:]', expr)

        singular = var.human_readable_name().lower()
        singular_parts = re.split(r'[\s:]', singular)
        if expr_parts == singular_parts:
            return True
        plural = inflect.engine().plural(singular)
        plural_parts = re.split(r'[\s:]', plural)
        if expr_parts == plural_parts:
            return True
        var_parts = re.split(r'[:\-]', var.var())
        if expr_parts == var_parts:
            return True
        # Don't require the user to specify the entity type.
        typeless_var = var.var().split(':', 1)[1]
        typeless_var_parts = re.split(r'[:\-]', typeless_var)
        if expr_parts == typeless_var_parts:
            return True

        return (re.fullmatch(expr, singular)
                or re.fullmatch(expr, plural)
                or re.fullmatch(expr, var.var())
                or re.fullmatch(expr, typeless_var))

    def _get_matches(self, expr, allowed_types):
        print("get_matches '" + expr + "'", allowed_types)
        allowed_vars = set()
        if "resource" in allowed_types:
            allowed_vars.update(
                [item for item in self._db.items().values() if item.is_resource()])
        if "item" in allowed_types:
            allowed_vars.update(
                [item for item in self._db.items().values() if not item.is_resource()])
        if "recipe" in allowed_types:
            allowed_vars.update(self._db.recipes().values())
        if "power-recipe" in allowed_types:
            allowed_vars.update(self._db.power_recipes().values())
        if "crafter" in allowed_types:
            allowed_vars.update(self._db.crafters().values())
        if "generator" in allowed_types:
            allowed_vars.update(self._db.generators().values())
        return [var for var in allowed_vars if QueryParser._check_var(expr, var)]

    def _parse_outputs(self, outputs, query):
        if not outputs:
            raise QueryParseException(
                "No outputs specified in optimization query.")
        for output in outputs:
            output_vars = []
            if "literal" in output:
                output_vars = [output["literal"]]
            if "entity" in output:
                output_vars.extend([var.var() for var in self._get_matches(
                    output["entity"], ["item"])])
                if len(output_vars) == 0:
                    raise QueryParseException(
                        "Could not parse entity expression '"
                        + output["entity"] + "'.")
            value = output["value"]
            if value == "?":
                if len(query.objective_coefficients) > 0:
                    raise QueryParseException(
                        "Only one objective may be specified.")
                query.maximize_objective = True
                query.objective_coefficients = {var: 1 for var in output_vars}
            elif value == "_":
                query.ge_constraints.update({var: 0 for var in output_vars})
            else:
                query.ge_constraints.update({var: value for var in output_vars})
            if output["strict"]:
                query.strict_outputs = True

    def _parse_inputs(self, inputs, query):
        if not inputs:
            query.maximize_objective = False
            query.objective_coefficients = {"unweighted-resources": -1}
            return
        for input_ in inputs:
            input_vars = []
            if "literal" in input_:
                input_vars = [input_["literal"]]
            elif "entity" in input_:
                input_vars.extend([var.var() for var in self._get_matches(
                    input_["entity"],
                    ["resource", "item"])])
                if len(input_vars) == 0:
                    raise QueryParseException(
                        "Could not parse entity expression '"
                        + input_["entity"] + "'.")
            value = input_["value"]
            if value == "?":
                if len(query.objective_coefficients) > 0:
                    raise QueryParseException(
                        "Only one objective may be specified.")
                query.maximize_objective = False
                query.objective_coefficients = {
                    var: -1 for var in input_vars}
            elif value == "_":
                query.le_constraints.update({var: 0 for var in input_vars})
            else:
                print(input_vars)
                query.ge_constraints.update(
                    {var: -value for var in input_vars})
            if input_["strict"]:
                query.strict_inputs = True

    def _parse_includes(self, includes, query):
        if not includes:
            return
        for include in includes:
            include_vars = []
            if "literal" in include:
                include_vars = [include["literal"]]
            elif "entity" in include:
                include_vars.extend([var.var() for var in self._get_matches(
                    include["entity"],
                    ["recipe", "power-recipe", "crafter", "generator"])])
                if len(include_vars) == 0:
                    raise QueryParseException(
                        "Could not parse entity expression '"
                        + include["entity"] + "'.")
            query.ge_constraints.update({var: 0 for var in include_vars})
            for var in include_vars:
                if var.startswith("recipe:"):
                    query.strict_recipes = True
                if var.startswith("power-recipe:"):
                    query.strict_power_recipes = True
                if var.startswith("crafter:"):
                    query.strict_crafters = True
                if var.startswith("generator:"):
                    query.strict_generators = True

    def _parse_excludes(self, excludes, query):
        if not excludes:
            return
        for exclude in excludes:
            exclude_vars = []
            if "literal" in exclude:
                exclude_vars = [exclude["literal"]]
            elif "entity" in exclude:
                exclude_vars.extend([var.var() for var in self._get_matches(
                    exclude["entity"],
                    ["recipe", "power-recipe", "crafter", "generator"])])
                if len(exclude_vars) == 0:
                    raise QueryParseException(
                        "Could not parse entity expression '"
                        + exclude["entity"] + "'.")
            query.eq_constraints.update({var: 0 for var in exclude_vars})

    def _parse_optimization_query(self, parse_results):
        query = OptimizationQuery()
        self._parse_outputs(parse_results.get("outputs"), query)
        self._parse_inputs(parse_results.get("inputs"), query)
        self._parse_includes(parse_results.get("includes"), query)
        self._parse_excludes(parse_results.get("excludes"), query)
        return query

    def _parse_recipes_for_query(self, parse_results):
        query = InfoQuery()
        matches = self._get_matches(
            parse_results.get("entity"),
            ["item", "crafter", "generator"])
        if len(matches) == 0:
            raise QueryParseException(
                "Could not parse entity expression '"
                + parse_results.get("entity") + "'.")
        for match in matches:
            var = match.var()
            if var.startswith("item") or var.startswith("resource"):
                for recipe in self._db.recipes_for_product(var):
                    query.vars.append(recipe)
            elif var.startswith("crafter"):
                for recipe in self._db.recipes().values():
                    if recipe.crafter().var() == var:
                        query.vars.append(recipe)
            elif var.startswith("generator"):
                for power_recipe in self._db.power_recipes().values():
                    if power_recipe.generator().var() == var:
                        query.vars.append(power_recipe)
        return query

    def _parse_recipes_from_query(self, parse_results):
        query = InfoQuery()
        matches = self._get_matches(parse_results.get("entity"),
                                    ["resource", "item"])
        if len(matches) == 0:
            raise QueryParseException(
                "Could not parse entity expression '"
                + parse_results.get("entity") + "'.")
        for match in matches:
            for recipe in self._db.recipes_for_ingredient(match.var()):
                query.vars.append(recipe)
        return query

    def _parse_entity_details(self, parse_results):
        query = InfoQuery()
        matches = self._get_matches(
            parse_results.get("entity-details"),
            ["resource", "item", "recipe", "power-recipe", "crafter",
                "generator"])
        if len(matches) == 0:
            raise QueryParseException(
                "Could not parse entity expression '"
                + parse_results.get("entity-details") + "'.")
        query.vars.extend(matches)
        return query

    def parse(self, raw_query):
        try:
            results = QueryParser.query_grammar.parseString(
                raw_query, parseAll=True)
        except ParseException as pe:
            raise QueryParseException(
                "\"" + raw_query + "\" ==> failed parse:\n" + (pe.loc+1)*" " +
                "^\n" + str(pe))

        print("\"" + raw_query + "\" ==> parsing succeeded:\n",
              results, "\n", results.dump(), "\n")

        if "optimization" in results:
            return self._parse_optimization_query(results)
        elif "recipes-for" in results:
            return self._parse_recipes_for_query(results)
        elif "recipes-from" in results:
            return self._parse_recipes_from_query(results)
        elif "entity-details" in results:
            return self._parse_entity_details(results)
        else:
            raise QueryParseException("Unknown query.")
