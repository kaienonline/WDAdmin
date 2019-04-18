# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from wduser.models import AuthUser, EnterpriseAccount, People, BaseOrganization
from assessment.models import AssessProject
import json
from collections import OrderedDict

class ChoicesField(serializers.Field):
    """Custom ChoiceField serializer field."""

    def __init__(self, choices, **kwargs):
        """init."""
        self._choices = OrderedDict(choices)
        super(ChoicesField, self).__init__(**kwargs)

    def to_representation(self, obj):
        """Used while retrieving value for the field."""
        return self._choices[obj]

    def to_internal_value(self, data):
        """Used while storing value for the field."""
        for i in self._choices:
            if self._choices[i] == data:
                return i
        raise serializers.ValidationError("Acceptable values are {0}.".format(list(self._choices.values()))) 

class BaseOrganizationSerializer(serializers.ModelSerializer):
    """organization information serializer"""

    enterprise_id = serializers.IntegerField()

    class Meta:
        model = BaseOrganization
        fields = ('id', 'enterprise_id', 'parent_id', 'name')

class UserSerializer(serializers.ModelSerializer):
    """user serializer"""
    sequence_name = serializers.CharField(source='sequence.name', read_only=True)
    gender_name = serializers.CharField(source='gender.name', read_only=True)
    rank_name = serializers.CharField(source='rank.name', read_only=True)
    marriage_name = serializers.CharField(source='marriage.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    enteprise = serializers.IntegerField(source='organization.enterprise_id', read_only=True)

    class Meta:
        model = AuthUser
        fields = ('id', 'nickname','role_type','phone','email','sequence',
                  'gender','rank','marriage','organization','enteprise',
                  'sequence_name','gender_name','rank_name','marriage_name',
                  'organization_name')

class AssessSerializer(serializers.ModelSerializer):
    '''Assessment Serializer'''
    distribute_type = ChoicesField(choices=AssessProject.DISTRIBUTE_CHOICES)
    assess_type =  ChoicesField(choices=AssessProject.TYPE_CHOICES)
    finish_choices =  ChoicesField(choices=AssessProject.FINISH_CHOICES)

    class Meta:
        model = AssessProject
        fields = ('id', 'name', 'en_name', 'enterprise_id', 'begin_time', 'end_time', 'advert_url', 'assess_type',
                  'project_status', 'finish_choices', 'finish_redirect', 'finish_txt', 'assess_logo', 'org_infos',
                  "user_count", "distribute_type", "has_distributed", 'is_answer_survey_by_order', 'has_survey_random',
                  'survey_random_number', 'show_people_info')
