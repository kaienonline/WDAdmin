# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger
from workspace.helper import OrganizationHelper
from workspace.serializers import UserSerializer,BaseOrganizationSerializer,AssessSerializer
from utils.regular import RegularUtils
from assessment.views import get_mima, get_random_char, get_active_code
from wduser.models import AuthUser, BaseOrganization, People, EnterpriseAccount, Organization
from assessment.models import AssessProject, AssessSurveyRelation, AssessProjectSurveyConfig, \
                              AssessSurveyUserDistribute,AssessUser, AssessOrganization, \
                              FullOrganization
from rest_framework.views import APIView                              
from front.models import PeopleSurveyRelation
from assessment.tasks import send_survey_active_codes
from django.db import connection,transaction,connections
from django.conf import settings
from survey.models import Survey

#retrieve logger entry for workspace app
logger = get_logger("workspace")

class UserLoginView(AuthenticationExceptView, WdCreateAPIView):
    """Login API for Workspace"""

    def post(self, request, *args, **kwargs):
        """get account,pwd field from request's data"""
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        #assure account and pwd be not empty
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        #continue unless account exists
        user, err_code = UserAccountUtils.account_check(account)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #continue unless account/pwd is correct
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #retrieve UserInfo Serialization
        user_info = UserSerializer(instance=user, context=self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)

class UserListCreateView(AuthenticationExceptView,WdCreateAPIView):
    """list/create person"""
    model = AuthUser
    serializer_class = UserSerializer

    def post(self, request, *args, **kwargs):
        pwd = request.data.get('password', None)
        phone = request.data.get('phone', None)
        email = request.data.get('email', None)
        nickname = request.data.get('nickname', None)
        account_name = request.data.get('account_name', None)
        organization_id = request.data.get('department', None)
        hiredate = request.data.get('hiredate', None)
        rank = request.data.get('rank', None)
        birthday = request.data.get('birthday', None)
        gender = request.data.get('gender', None)
        sequence = request.data.get('sequence', None)
        marriage = request.data.get('marriage', None)
        is_staff = request.data.get('is_staff', True)
        role_type = request.data.get('role_type', AuthUser.ROLE_NORMAL)
        is_superuser = request.data.get('is_superuser', False)
        username = nickname + get_random_char(6)
        active_code = get_active_code()
        
        organization = BaseOrganization.objects.get(pk=organization_id)
        enterprise_id = organization.enterprise_id

        #check account_name not duplicated
        if account_name:
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       account_name=account_name,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})
        #retrieve phone
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'新增用户失败，手机格式有误'})
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       phone=phone,
                                       organization__is_active=True).exists():                       
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'新增用户失败，手机已被使用'})
        #retrieve email                                
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'新增用户失败，邮箱格式有误'})
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_USED_ERROR,
                                             {'msg': u'新增用户失败，邮箱已被使用'})

        try:
            #create user object
            user = AuthUser.objects.create(
                username=username,
                account_name=account_name,
                nickname=nickname,
                password=get_mima(pwd),
                phone=phone,
                email=email,
                is_superuser=is_superuser,
                role_type=role_type,
                is_staff=is_staff,
                sequence_id=sequence,
                gender_id=gender,
                birthday=birthday,
                rank_id=rank,
                hiredate=hiredate,
                marriage_id=marriage,
                organization_id=organization.id
            )

            #create people object
            people = People.objects.create(user_id=user.id, 
                                           username=account_name, 
                                           phone=phone,
                                           email=email)
            #create enterprise-account object
            EnterpriseAccount.objects.create(user_id=user.id,
                                             people_id=people.id,
                                             account_name=account_name,
                                             enterprise_id=enterprise_id)

            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u'成功'})
        except Exception, e:
            logger.error("新增用户失败 %s" % e.message)
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {'msg': u'新增用户失败:%s' % e.message})

    def get(self, request, *args, **kwargs):
        '''list users'''
        
        tree_ids = [request.GET.get('organization_id')] + OrganizationHelper.get_child_ids(request.GET.get('organization_id'))
        if tree_ids:
            users = UserSerializer(AuthUser.objects.filter(is_active=True,
                                                           baseorganization__in=tree_ids,
                                                           baseorganization__is_active=True),
                                   many=True)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": users.data})
        else:
            return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.NOT_EXISTED)  
        
class UserDetailView(AuthenticationExceptView,WdRetrieveUpdateAPIView,WdDestroyAPIView):
    '''person detail management'''
    model = AuthUser
    serializer_class = UserSerializer

    def put(self, request, *args, **kwargs):
        '''update user's profile, password ,email ,phone and organization'''
        user = self.get_object()

        phone = request.data.get('phone', None)
        email = request.data.get('email', None)
        account_name = request.data.get('account_name', None)
        nickname = request.data.get('username', None)
        pwd = request.data.get('password', None)
        password = get_mima(pwd) if pwd else None
        organization_id = request.data.get('department', None)
        hiredate = request.data.get('hiredate', None)
        rank = request.data.get('rank', None)
        birthday = request.data.get('birthday', None)
        gender = request.data.get('gender', None)
        sequence = request.data.get('sequence', None)
        marriage = request.data.get('marriage', None)
        is_staff = request.data.get('is_staff', True)
        role_type = request.data.get('role_type', AuthUser.ROLE_NORMAL)        

        if account_name and (account_name != user.account_name):
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       account_name=account_name,
                                       organization__is_active=True).exists(): 
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})

        #check user phone
        if phone and (phone != user.phone):
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'手机格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       phone=phone,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                                {'msg': u'手机已被使用'})
        #check user email
        if email and (email != user.email):
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'邮箱格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exists(): 
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'邮箱已被使用'})
        #user entity          
        user.account_name = account_name
        user.nickname = nickname
        user.phone = phone
        user.email = email
        if password:
            user.password = password
        user.hiredate = hiredate
        user.rank_id = rank
        user.birthday = birthday
        user.gender_id = gender
        user.sequence_id = sequence
        user.marriage_id = marriage
        user.is_staff = is_staff
        user.role_type = role_type
        user.organization_id = organization_id

        try:
            user.save()
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        except Exception, e:
            logger.error("update %d error %s" % (user.id, e))
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_UPDATE_ERROR, {'msg': u'modification error'})

    def delete(self, request, *args, **kwargs):
        '''delete users profile'''
        user = self.get_object()
        user.is_active=False
        user.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class OrganizationListCreateView(AuthenticationExceptView, WdCreateAPIView):
    """organization tree view"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer
    GET_CHECK_REQUEST_PARAMETER = {"organization_id"}

    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        tree_orgs = OrganizationHelper.get_tree_orgs(self.organization_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": tree_orgs})

class OrganizationlRetrieveUpdateDestroyView(AuthenticationExceptView,
                                             WdRetrieveUpdateAPIView, WdDestroyAPIView):
    """organization management"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer

    def delete(self, request, *args, **kwargs):
        
        org = self.get_id()
        org_ids = [org] + OrganizationHelper.get_child_ids(org)

             
        #delete all organizations only when no active member exists
        if BaseOrganization.objects.filter_active(pk__in=org_ids,
                                                  users__is_active=True).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.WORKSPACE_ORG_MEMBEREXISTS)
        else:
            for org in BaseOrganization.objects.filter(id__in=org_ids):
                org.users.clear()   
            BaseOrganization.objects.filter(id__in=org_ids).update(is_active=False)
            
            logger.info('user_id %s want delete orgs %s' % (self.request.user.id,org_ids))
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class OrganizationImportExportView(AuthenticationExceptView):
    """organization template import/export"""
    def get_template(self):
        #todo
        """get template file"""

    def post(self, request, *args, **kwargs):
        #todo
        """import organization file"""

class AssessCreateView(AuthenticationExceptView, WdListCreateAPIView):
    '''create assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    POST_CHECK_REQUEST_PARAMETER={"name","distribute_type","surveys"}

    SURVEY_DISC = 89
    SURVEY_OEI = 147
    SURVEY_IEC = 163
    ASSESS_STA = 286

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        distribute_type = request.data.get('distribute_type')
        surveys = request.data.get('surveys').split(",")
        assess = AssessProject.objects.create(name=name,
                                              distribute_type=distribute_type)

        for survey in surveys:
            AssessSurveyRelation.objects.create(assess_id=assess.id,survey_id=survey)
            if int(survey) == self.SURVEY_OEI:
                qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=survey,
                                                                     assess_id=self.ASSESS_STA).all()
                for x in qs:
                    x.id = None
                    x.assess_id=assess.id
                AssessProjectSurveyConfig.objects.bulk_create(qs)

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessDetailView(AuthenticationExceptView, WdCreateAPIView):
    '''update/delete assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    def delete(self, request, *args, **kwargs):
        assess = self.get_object()
        assess.is_active = False
        assess.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessSurveyRelationDistributeView(AuthenticationExceptView,WdCreateAPIView):

    model = AssessSurveyRelation
    POST_CHECK_REQUEST_PARAMETER = ("enterprise_id","user_id","org_ids" )
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )

    def get_all_survey_finish_people_count(self, finish_people_ids, assess_id):
        not_finish_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=finish_people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_NOT_BEGIN,
                                                                          PeopleSurveyRelation.STATUS_DOING,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART,
                                                                          PeopleSurveyRelation.STATUS_EXPIRED
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        f_count = len(finish_people_ids) - not_finish_count
        return f_count

    def get_doing_survey_people_count(self, people_ids, assess_id):
        beign_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_FINISH,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        not_count = len(people_ids) - beign_count
        return not_count

    def send_active_code(self, people_ids):
        send_survey_active_codes.delay(people_ids)

    def distribute_normal(self,assess_id,enterprise_id,user_id,orgid_list):

        #todo check no duplication of assess

        #retrieve assessment status
        assessment_obj = AssessProject.objects.get(id=assess_id)
        if assessment_obj.project_status == AssessProject.STATUS_WORKING:
            status = PeopleSurveyRelation.STATUS_DOING
        else:
            status = PeopleSurveyRelation.STATUS_NOT_BEGIN
        
        sql_attach = 'insert into wduser_peopleorganization select null,now(), \
                        true,now(),%s,%s, d.id,c.id \
                        from wduser_authuser a, \
		                wduser_baseorganization b, \
		                wduser_organization c,\
		                wduser_people d \
	                    where b.id=c.baseorganization_id \
		                and a.organization_id=b.id \
		                and d.user_id=a.id \
                        and a.is_active=true \
                        and b.is_active=true \
                        and c.is_active=true \
                        and d.is_active=true'
        sql_attach2 = 'insert into assessment_assessuser \
	                   select null,now(),true,now(),%s,%s,%s,people_id,10,0 \
                       from wduser_peopleorganization a \
                       inner join wduser_organization b \
                       on binary a.org_code= b.identification_code \
                       where assess_id=%s \
                       and a.is_active=true and b.is_active=true'
        sql_attach3 = 'insert into '+ settings.FRONT_HOST +'.front_peoplesurveyrelation \
                        (`id`,`create_time`,`is_active`,`update_time`,`creator_id`,`last_modify_user_id`,`people_id`,\
                        `survey_id`,`project_id`,`role_type`,`evaluated_people_id`,`survey_name`,`status`,`begin_answer_time`,\
                        `finish_time`,`is_overtime`,`report_status`,`report_url`,`model_score`,`dimension_score`,\
                        `substandard_score`,`happy_score`,`en_survey_name`,`praise_score`,`facet_score`,`happy_ability_score`,\
                        `happy_efficacy_score`,`uniformity_score`,`en_report_url`) \
                        select null,now(),true,now(),\
                        %s,%s,people_id,%s,%s,10,0,%s,10,null,null,0,0,null,0\
                        ,null,null,0,null,0,null,0,0,null,null\
                        from wduser_peopleorganization a \
                        inner join wduser_organization b \
                        on binary a.org_code=b.identification_code \
                        where assess_id=%s \
                        and a.is_active=true and b.is_active=true'

        #copy base organization into assess organization
        with connection.cursor() as cursor:
            ret = cursor.callproc("CopyOrganization", (enterprise_id,assess_id,user_id))                

        orgs = Organization.objects.filter(baseorganization_id__in=list(orgid_list),assess_id=assess_id)
        orgs.update(is_active=True)
        FullOrganization.objects.filter(organization_id__in=orgs.values_list("id",flat=True)).update(is_active=True)  

        #attach user to assessment
        with connection.cursor() as cursor:
            cursor.execute(sql_attach, [user_id,user_id])
            cursor.execute(sql_attach2, [user_id,user_id,assess_id,assess_id])
            people_ids = map(int,list(AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct().all()))
            for survey in AssessSurveyRelation.objects.filter_active(assess_id=assess_id).values_list("survey_id", flat=True):
                surveyname = Survey.objects.get(pk=survey).title
                cursor.execute(sql_attach3, [user_id,user_id,survey,assess_id,surveyname,assess_id])                
                AssessSurveyUserDistribute.objects.create(assess_id=assess_id, survey_id=survey, people_ids=people_ids)

        #send sms information
        self.send_active_code(people_ids)  

        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        self.assessment = AssessProject.objects.get(id=self.kwargs.get('pk'))
        assess_id = self.assessment.id
        enterprise_id = self.request.data.get("enterprise_id")        
        user_id = self.request.data.get("user_id")
        orgid_list = map(int,self.request.data.get("org_ids").split(",") )       
        rst_code = self.distribute_normal(assess_id,enterprise_id,user_id,orgid_list)
        return general_json_response(status.HTTP_200_OK, rst_code)

    def get_project_url(self):
        project_id_bs64 = quote(base64.b64encode(str(self.assess_id)))
        return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)

    def get_import_project_user_statistics(self):
        po_qs = AssessUser.objects.filter_active(assess_id=self.assess_id).values_list("people_id", flat=True).distinct()
        all_count = po_qs.count()
        user_qs = PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id)
        people_ids = user_qs.values_list('people_id', flat=True).distinct()
        wei_fen_fa = all_count - people_ids.count() 
        yi_wan_cheng = self.get_all_survey_finish_people_count(list(people_ids), self.assess_id)
        yi_fen_fa = self.get_doing_survey_people_count(list(people_ids), self.assess_id)
        da_juan_zhong = people_ids.count() - yi_wan_cheng - yi_fen_fa
        distribute_count = people_ids.count()
        return {
            "count": all_count,
            "doing_count": da_juan_zhong,
            "not_begin_count": yi_fen_fa,
            "finish_count": yi_wan_cheng,
            "not_started": wei_fen_fa,
            "distribute_count": distribute_count 
        }

    def get_distribute_info(self):
        project = AssessProject.objects.get(id=self.assess_id)
        user_statistics = self.get_import_project_user_statistics()
        org_ids = AssessOrganization.objects.filter_active(
            assess_id=self.assess_id).values_list("organization_id", flat=True)
        org_infos = Organization.objects.filter_active(id__in=org_ids).values("id", "name", "identification_code")
        return {
            "user_statistics": user_statistics,
            "org_infos": org_infos
        }

    def get(self, request, *args, **kwargs):
        data = {
            "url": self.get_project_url(),
            "distribute_info": self.get_distribute_info()
        }
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)

class AssessProgressView(AuthenticationExceptView,APIView):

    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')
        depth = 1        

        with connection.cursor() as cursor:
            cursor.execute("SELECT getdepth(%s) as depth", [orgid])
            row = cursor.fetchone()
            depth = row[0]
            parent_field = "organization" + str(depth)
            child_field = "organization" + str(depth+1)
            sql_query = "select ifnull(" +child_field +",%s) as id,\
                        max(d.name) as name, \
                        count(c.people_id) total, max(a.is_active) valid,\
                        sum(CASE c.status WHEN 20 THEN 1 ELSE 0 END) finished \
                        from assessment_fullorganization a \
                        inner join wduser_peopleorganization b \
                        on a.organization_id=b.org_code \
                        and b.is_active=true \
                        left join " + settings.FRONT_HOST + ".front_peoplesurveyrelation c \
                        on b.people_id=c.people_id \
                        and c.is_active=true \
                        and a.assess_id=c.project_id \
                        inner join wduser_organization d \
                        on a.organization_id=d.id \
                        and d.is_active=true \
                        where a.assess_id=%s \
                        and a."+ parent_field + "=%s \
                        and c.survey_id=%s \
                        group by " +child_field + " order by id"            
            cursor.execute(sql_query, [orgid,assess,orgid,survey])
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
        data = {"progress" : results}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)

class AssessProgressTotalView(AuthenticationExceptView,APIView):

    def get(self, request, *args, **kwargs):
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        organization = Organization.objects.filter(assess_id=assess,parent_id=0).first()

        with connection.cursor() as cursor:
            sql_query = "select %s  as id,max(d.name) as name, \
                        count(c.people_id) total,max(a.is_active) valid,\
                        sum(CASE c.status WHEN 20 THEN 1 ELSE 0 END) finished \
                        from assessment_fullorganization a \
                        inner join wduser_peopleorganization b \
                        on a.organization_id=b.org_code \
                        and b.is_active=true \
                        left join "+ settings.FRONT_HOST + ".front_peoplesurveyrelation c \
                        on b.people_id=c.people_id \
                        and c.is_active=true \
                        inner join wduser_organization d \
                        on a.organization_id=d.id \
                        and d.is_active=true \
                        and a.assess_id=c.project_id \
                        where a.assess_id=%s \
                        and a.organization1=%s \
                        and c.survey_id=%s "
                        
            cursor.execute(sql_query, [organization.id,assess,organization.id,survey])
            columns = [column[0] for column in cursor.description]
            result= dict(zip(columns, cursor.fetchone()))          
        data = {"progress" : result}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)