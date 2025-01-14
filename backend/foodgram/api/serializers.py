from base64 import b64decode
from uuid import uuid4

from django.core.files.base import ContentFile
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from recipies.models import (Favorite, Ingredient, IngredientInRecipe, Recipe,
                             ShoppingCart, Tag)
from users.serializers import CustomUserSerializer
from .utils import add_tags_to_instance, check_for_dublicates


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')


class IngredientInRecipeSerializer(serializers.ModelSerializer):
    id = serializers.PrimaryKeyRelatedField(
        queryset=Ingredient.objects.all(),
        source='ingredient'
    )
    name = serializers.ReadOnlyField(source='ingredient.name')
    measurement_unit = serializers.ReadOnlyField(
        source='ingredient.measurement_unit')

    class Meta:
        model = IngredientInRecipe
        fields = ('id', 'name', 'measurement_unit', 'amount')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'color', 'slug')


class RecipeSerializer(serializers.ModelSerializer):
    author = CustomUserSerializer(
        read_only=True,
        default=serializers.CurrentUserDefault()
    )
    ingredients = IngredientInRecipeSerializer(many=True)
    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()

    def get_is_favorited(self, obj):
        return Favorite.objects.filter(
            user=self.context['request'].user.id,
            recipe=obj.id
        ).exists()

    def get_is_in_shopping_cart(self, obj):
        return ShoppingCart.objects.filter(
            user=self.context['request'].user.id,
            recipe=obj.id
        ).exists()

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'is_favorited',
            'is_in_shopping_cart',
            'name',
            'image',
            'text',
            'cooking_time'
        )

        validators = [
            UniqueTogetherValidator(
                queryset=Recipe.objects.all(),
                fields=('name', 'author'),
                message='Вы уже создавали такой рецепт.',
            )
        ]

    def validate(self, data):
        ingredients = (
            [ingredient['ingredient'].id for ingredient in data['ingredients']]
        )
        tags = data['tags']
        check_for_dublicates(
            items_list=ingredients,
            error_message='Ингредиенты дублируются')
        check_for_dublicates(
            items_list=tags,
            error_message='Тэги дублируются')
        return data

    def to_internal_value(self, data):
        if 'image' in data:
            format, imgstr = data['image'].split(';base64,')
            ext = format.split('/')[-1]
            file_name = str(uuid4())
            img_file = ContentFile(
                b64decode(imgstr), name=f'{file_name}.{ext}'
            )

            data['image'] = img_file
        return super().to_internal_value(data)

    def create(self, validated_data):
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredients')
        new_recipe = Recipe.objects.create(**validated_data)
        ingredients_objects_list = ([IngredientInRecipe(
            ingredient=ingredient.get('ingredient'),
            amount=ingredient.get('amount')) for ingredient in ingredients])
        IngredientInRecipe.objects.bulk_create(
            ingredients_objects_list,
            ignore_conflicts=True
        )
        ingredients_queryset = IngredientInRecipe.objects.filter(
            ingredient__in=([item.ingredient
                            for item in ingredients_objects_list]),
            amount__in=[item.amount for item in ingredients_objects_list]
        )
        new_recipe.ingredients.set(ingredients_queryset)
        add_tags_to_instance(new_recipe, tags)
        return new_recipe

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags')
        instance.tags.clear()
        add_tags_to_instance(instance, tags)
        ingredients = validated_data.pop('ingredients')
        instance.ingredients.clear()
        for ingredient in ingredients:
            ingredient_in_recipe, create = (
                IngredientInRecipe.objects.get_or_create(**ingredient)
            )
            instance.ingredients.add(ingredient_in_recipe)
        return super().update(instance, validated_data)


class RecipeGetSerializer(RecipeSerializer):
    tags = TagSerializer(many=True)


class RecipePostSerializer(RecipeSerializer):
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True
    )


class FavoriteSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='recipe.id')
    name = serializers.ReadOnlyField(source='recipe.name')
    image = serializers.SerializerMethodField()
    cooking_time = serializers.ReadOnlyField(source='recipe.cooking_time')

    def get_image(self, obj):
        request = self.context.get('request')
        image_url = obj.recipe.image.url
        return request.build_absolute_uri(image_url)

    class Meta:
        model = Favorite
        fields = ('id', 'name', 'image', 'cooking_time')


class ShoppingCartSerializer(FavoriteSerializer):
    class Meta:
        model = ShoppingCart
        fields = ('id', 'name', 'image', 'cooking_time')
