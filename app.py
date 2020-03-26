import json
from flask import Flask, request, make_response, jsonify
import requests
from string import Template
import infermedica_api
import os

infermedica_app_id =  os.getenv("infermedica_app_id")
infermedica_app_key = os.getenv("infermedica_app_key")

infermedica_api.configure(
    {'app_id': infermedica_app_id, 'app_key': infermedica_app_key, 'dev_mode': True})

app = Flask(__name__)
log = app.logger

options_dict = {
    "yes": "present",
    "no": "absent",
    "dontknow": "unknown",
}
image_url = {
    "present":"https://cdn2.iconfinder.com/data/icons/check-mark-style-1/1052/check_mark_voting_yes_no_24-512.png",
    "absent":"https://cdn2.iconfinder.com/data/icons/check-mark-style-1/1052/check_mark_voting_yes_no_13-512.png",
    "unknown":"https://www.pngfind.com/pngs/m/81-815205_question-face-blinking-emoji-emoji-angry-png-transparent.png",
}
card_tmpl = """{
"optionInfo": {
"key":"$key",
"synonyms": [
"$name",
"select $name",
"choose $name"
]
},
"description": "$name",
"image": {
"url": "$imageurl",
"accessibilityText": "first alt"
},
"title": "$name"
}
"""
card_tmpl = Template(card_tmpl)

@app.route('/', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    print(req)
    intent_name = req["queryResult"]["intent"]["displayName"]

    if intent_name == "Default Welcome Intent":
        response_text = 'Hi, welcome to "Infermedica Health Check". To begin with May I know your Gender and Age?'

    elif intent_name == "GetAgeGender":
        ctx = getContext(req)
        print(ctx)
        age = ctx["getagegender"]["parameters"]["age"]["amount"]
        gender = ctx["getagegender"]["parameters"]["Gender"]
        response_text = "Ok, Thanks, Share me how do you feel right now. What problems do you have ?"
        return make_response(jsonify({"fulfillmentText": response_text}))

    elif intent_name == "GetSymptoms":
        ctx = getContext(req)

        if ctx["getagegender"]:
            ctx["getagegender"]["lifespanCount"] = 1
            age = int(ctx["getagegender"]["parameters"]["age"]["amount"])
            gender = ctx["getagegender"]["parameters"]["Gender"]

        nlp_query = req["queryResult"].get("queryText", "")
        symptoms_found_by_infermedia = get_symptoms_nlp(nlp_query)
        print('>>> : symptoms_found_by_infermedia["mentions"] : ',
              symptoms_found_by_infermedia["mentions"], '\n')

        if not symptoms_found_by_infermedia['mentions']:
            response_text = 'Please give some more brief decription of how you feel ?'
            outputContexts = add_new_context(req, ctx, "getSymptomsInvalid", 1)
            return make_response(jsonify({'fulfillmentText': response_text, 'outputContexts': outputContexts, }))

        # set a new context for count ...
        addedcontext  = add_new_context(req, ctx, "questioncount", 3, {
            "question_count": 1
        })
        req["queryResult"]["outputContexts"] = addedcontext
        ctx = getContext(req)

        respdict = diagnostics(gender, age, symptoms_found_by_infermedia["mentions"])

        # return the valid response of prediction ...
        if check_probability (respdict,ctx): return make_response(make_response_basedon_conditions(respdict, req, ctx, age, gender)) 
        return make_response(make_response_basedon_questiontype(respdict, req, ctx, age, gender))

    elif intent_name == "SingleQuestionOptions":
        ctx = getContext(req)
        print(ctx)
        data = ctx["singlequestionoptions"]["parameters"]["data"]
        age = data["age"]
        gender = data["gender"]
        choice_id = ctx["singlequestionoptions"]["parameters"]["choice_id"]
        yes_no_dontknow = ctx["singlequestionoptions"]["parameters"]["yes_no_dontknow"]
        options_selected = options_dict[yes_no_dontknow.lower()]
        data["symp_list"].append({
            "id": choice_id,
            "choice_id": options_selected
        })
        respdict = diagnostics(gender, age, data["symp_list"])

        if check_probability (respdict,ctx): return make_response(make_response_basedon_conditions(respdict, req, ctx, age, gender)) 
        return make_response(make_response_basedon_questiontype(respdict, req, ctx, age, gender))
    

    elif intent_name =="GroupSingleQuestionOptions":
        ctx = getContext(req)
        print(ctx)
        data = ctx["groupsinglequestionoptions"]["parameters"]["data"]
        age = data["age"]
        gender = data["gender"]
        choice_id = ctx["groupsinglequestionoptions"]["parameters"]["choice_id"]
        groupsingleoption = ctx["groupsinglequestionoptions"]["parameters"]["groupsingleoption"]
        _options_dict = {keyvalue[0]:keyvalue[1] for keyvalue in [combination.split(':') for combination in choice_id.split(',')]}
        data["symp_list"].append({
                "id": _options_dict[groupsingleoption] ,
                "choice_id": options_dict['yes'] 
            })
        respdict = diagnostics(gender, age, data["symp_list"])

        if check_probability (respdict,ctx): return make_response(make_response_basedon_conditions(respdict, req, ctx, age, gender)) 
        return make_response(make_response_basedon_questiontype(respdict, req, ctx, age, gender))

    elif intent_name =="OptionSelectQuestionOptions":
        ctx= getContext(req)
        print(ctx)
        if "optionselectquestionoptions" in ctx:
            question_type = ctx["optionselectquestionoptions"]["parameters"]["question_type"]
            if question_type == "single":
                data = ctx["optionselectquestionoptions"]["parameters"]["data"]
                age = data["age"]
                gender = data["gender"]
                choice_id = ctx["optionselectquestionoptions"]["parameters"]["choice_id"]
                options_selected = ctx["actions_intent_option"]["parameters"]["OPTION"]
                data["symp_list"].append({
                    "id": choice_id,
                    "choice_id": options_selected
                })
                respdict = diagnostics(gender, age, data["symp_list"])

                if check_probability (respdict,ctx): return make_response(make_response_basedon_conditions(respdict, req, ctx, age, gender)) 
                return make_response( make_response_basedon_questiontype(respdict, req, ctx, age, gender))
            else:
                data = ctx["optionselectquestionoptions"]["parameters"]["data"]
                age = data["age"]
                gender = data["gender"]
                options_selected = ctx["actions_intent_option"]["parameters"]["OPTION"]
                data["symp_list"].append({
                        "id": options_selected ,
                        "choice_id": options_dict['yes'] 
                    })
                respdict = diagnostics(gender, age, data["symp_list"])

                if check_probability (respdict, ctx): return make_response(make_response_basedon_conditions(respdict, req, ctx, age, gender))    
                return make_response(make_response_basedon_questiontype(respdict, req, ctx, age, gender))
        else:
            response_text = "OptionSelectSingleQuestionOptions............FAILED NO OPTIONS SELECTED"

    else:
        print(">>>>>> no intent matched "+str(getContext(req)))
        response_text = "No intent matched"

    return make_response(jsonify({'fulfillmentText': response_text}))

# --------------------------------------------------------------------------------------------------------------------------------
def check_probability(respdict, ctx):
    question_count = ctx["questioncount"]["parameters"]["question_count"] 
    if len(respdict["conditions"])<= 3  or int(respdict["conditions"][0]["probability"]) >= 0.7 or question_count >= 10:
        return True
    return False

def make_response_basedon_conditions(respdict, req, ctx, age, gender):
    conditions  = ", ".join([i["common_name"] for i in respdict["conditions"]])
    return jsonify({
        'fulfillmentText': f"You may be suffering by any one of the following : {conditions}. Consider Visiting the Hospital if you feel sick. Is there anything else you wish to check ?",
         "outputContexts": add_new_context(req, ctx, "getagegender", 1, {
            "age": {"amount":age},
            "Gender": gender,
            }), 
    })

def make_response_basedon_questiontype(respdict, req, ctx, age, gender):
    ctx["questioncount"]["lifespanCount"] =  2
    ctx["questioncount"]["parameters"]["question_count"] = int(ctx["questioncount"]["parameters"]["question_count"]) + 1 
    print( ctx["questioncount"]["lifespanCount"] , ctx["questioncount"]["parameters"]["question_count"] )
    display_type = ''
    if req["originalDetectIntentRequest"]["payload"]:
        if req["originalDetectIntentRequest"]["payload"]["availableSurfaces"][0]["capabilities"]:
            if "actions.capability.SCREEN_OUTPUT" in [i["name"] for i in req["originalDetectIntentRequest"]["payload"]["availableSurfaces"][0]["capabilities"]]:
                display_type = "TOUCHDISPLAY"

    if respdict["question_type"] == 'single':
        # --------------------
        if display_type=="TOUCHDISPLAY":
            r = handle_type_single_TOUCHDISPLAY(respdict, req, ctx, age, gender)
            return jsonify( listSelect( r["response_text_question_to_followup"], r['outputContexts'], r["item_list"], r["choice_name"] ) )
        else:
            r = handle_type_single(respdict, req, ctx, age, gender)
            return jsonify({'fulfillmentText': r["response_text_question_to_followup"]+" " + r['choice_options_str'], 'outputContexts': r['outputContexts']})
        # --------------------

    elif respdict["question_type"] == 'group_single' or respdict["question_type"] == 'group_multiple':
        # --------------------
        if display_type=="TOUCHDISPLAY":
            r = handle_type_group_single_TOUCHDISPLAY(respdict, req, ctx, age, gender)
            return jsonify( listSelect( r["response_text_question_to_followup"], r['outputContexts'], r["item_list"],r["response_text_question_to_followup"] ) )
        else:
            r = handle_type_group_single(respdict, req, ctx, age, gender)
            return jsonify({'fulfillmentText': r["response_text_question_to_followup"]+" " + r['choice_options_str'], 'outputContexts': r['outputContexts']})
        # --------------------
    else:
        return jsonify({'fulfillmentText': "question type : "+respdict["question_type"]})



def handle_type_group_single_TOUCHDISPLAY(respdict, req, ctx, age, gender):
    data={
        "response_text_question_to_followup": respdict["question"],
        "choice_name":", ".join([ str(index+1) + " : " + item["name"] for index,item in enumerate(respdict["item"])]),
        "item_list" : [  json.loads( card_tmpl.substitute(
            key =item.get("id"), 
            name= item.get("name") , 
            imageurl=image_url["unknown"]
             ) )  for item in respdict["item"] ] ,
        "outputContexts": add_new_context(req, ctx, "optionselectquestionoptions", 1, {
            "question_type":"group_single",
            "data": {
                "age": age,
                "gender": gender,
                "symp_list": respdict["symptoms"],
                "question_count": ctx["questioncount"]["parameters"]["question_count"]
            }}), 
    }
    return data

def handle_type_single_TOUCHDISPLAY(respdict, req, ctx, age, gender):
    data={
        "response_text_question_to_followup": respdict["question"],
        "choice_id": respdict["item"][0]["id"],
        "choice_name": respdict["item"][0]["name"],
        "item_list" : [  json.loads( card_tmpl.substitute(
            key =item.get("id"), 
            name= item.get("label") , 
            imageurl=image_url[item.get("id")] ) )  for item in respdict["item"][0]["choices"] ] ,
        "outputContexts": add_new_context(req, ctx, "optionselectquestionoptions", 1, {
            "choice_id": respdict["item"][0]["id"], 
            "question_type":"single",
            "data": {
                "age": age,
                "gender": gender,
                "symp_list": respdict["symptoms"],
                "question_count": ctx["questioncount"]["parameters"]["question_count"]
            }}), 
    }
    return data

def handle_type_single(respdict, req, ctx, age, gender):
    data = {
        "response_text_question_to_followup": respdict["question"],
        "choice_name": respdict["item"][0]["name"],
        "choice_id": respdict["item"][0]["id"],
        "choice_options": respdict["item"][0]["choices"],
        "choice_options_str": ", ".join([i['label'] for i in respdict["item"][0]["choices"]]),
        "outputContexts": add_new_context(req, ctx, "singlequestionoptions", 1, {"choice_id": respdict["item"][0]["id"], "data": {
            "age": age,
            "gender": gender,
            "symp_list": respdict["symptoms"],
            "question_count": ctx["questioncount"]["parameters"]["question_count"]
        }})
    }
    return data

def handle_type_group_single(respdict, req, ctx, age, gender):
    data = {
        "response_text_question_to_followup": respdict["question"],
        "choice_name": ", ".join([ str(index+1) + " : " + item["name"] for index,item in enumerate(respdict["item"])]),
        "choice_id": ",".join([ str(index+1) +":"+item["id"] for index,item in enumerate(respdict["item"])]),
    }
    data["choice_options"] = data["choice_name"]
    data["choice_options_str"]= data["choice_name"]
    data["outputContexts"]= add_new_context(req, ctx, "groupsinglequestionoptions", 1, {"choice_id": data["choice_id"], "data": {
            "age": age,
            "gender": gender,
            "symp_list": respdict["symptoms"],
            "question_count": ctx["questioncount"]["parameters"]["question_count"]
        }})
    return data


def getContext(req):
    ctx_tmp = {}
    for each_context in req["queryResult"]["outputContexts"]:
        ctx_tmp[each_context["name"].split("/")[-1]] = [each_context][0]
    return ctx_tmp


def add_new_context(req, ctx, new_context_name, lifespanCount, parameters={}):
    tmp = [{
        "name":  req["queryResult"]["outputContexts"][0].get("name").split("/contexts/")[0] + "/contexts/" + new_context_name,
        "lifespanCount": lifespanCount,
        "parameters": parameters
    }]
    return list(ctx.values()) + tmp


def get_symptoms_nlp(text):
    headers = {
        "App-Id": infermedica_app_id,
        "App-Key": infermedica_app_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text
    }
    r = requests.post("https://api.infermedica.com/v2/parse",
                      data=json.dumps(payload), headers=headers)
    return r.json()


def diagnostics(sex_, age_, symp_list):
    api = infermedica_api.get_api()
    request = infermedica_api.Diagnosis(sex=sex_, age=int(age_))
    for symptom in symp_list:
        request.add_symptom(symptom["id"], symptom["choice_id"],
                            initial=True if symptom['choice_id'] == 'present' else False)

    response = api.diagnosis(request)
    return {
        "question": response.question.text,
        "question_type": response.question.type,
        "should_stop": response.should_stop,
        "symptoms": response.symptoms,
        "item": response.question.items,
        "conditions":response.conditions,
    }

# ----------------------------------------------------------------------

def listSelect(response_text, outputContexts, item_list , item_list_title = "" ):
    dict_ = {
            'fulfillmentText': response_text, 
            "fulfillmentMessages": [],
            'outputContexts': outputContexts,
            "payload": {
            "google": {
            "expectUserResponse": True,
            "richResponse": {
                "items": [
                {
                    "simpleResponse": {
                    "textToSpeech": response_text
                    }
                }
                ]
            },
            "systemIntent": {
                "intent": "actions.intent.OPTION",
                "data": {
                "@type": "type.googleapis.com/google.actions.v2.OptionValueSpec",
                "listSelect": {
                    "title": item_list_title,
                    "items": item_list ,
                    }
                }
            }
            }
        }
    }
    return dict_

# ---------------------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv("PORT"))
