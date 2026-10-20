"""Synthetic SSE producer shared by offline tests and manual loopback evidence.

This helper never invokes a client, provider, database, or external process.
"""

import json


def synthetic_stream(stage: int, *, model: str = 'qwen3.8-27b') -> list[dict]:
    response_id = f'resp_synthetic_preset_{stage}'
    events = []
    output = []

    def emit(kind, **values):
        events.append({'type':kind,'sequence_number':len(events),**values})

    progress = {'id':response_id,'status':'in_progress','model':model}
    emit('response.created',response=progress)
    emit('response.in_progress',response=progress)

    def message(text):
        index = len(output)
        item_id = f'msg_synthetic_{stage}_{index}'
        item = {'type':'message','id':item_id,'status':'in_progress','role':'assistant',
                'content':[],'phase':None}
        emit('response.output_item.added',output_index=index,item=item)
        coordinates = {'item_id':item_id,'output_index':index,'content_index':0}
        emit('response.content_part.added',**coordinates,
             part={'type':'output_text','text':'','annotations':[],'logprobs':[]})
        emit('response.output_text.delta',**coordinates,delta=text,logprobs=[])
        emit('response.output_text.done',**coordinates,text=text,logprobs=[])
        part = {'type':'output_text','text':text,'annotations':[],'logprobs':None}
        emit('response.content_part.done',**coordinates,part=part)
        done = dict(item,status='completed',content=[part],summary=[])
        emit('response.output_item.done',output_index=index,item=done)
        output.append({k:v for k,v in done.items() if k!='summary'})

    if stage == 0:
        message('I will run the synthetic local tool once.')
        index = len(output)
        arguments = json.dumps({'cmd':'printf PRESET_TOOL_OK'})
        item = {'type':'function_call','id':'fc_synthetic_preset','call_id':'call_synthetic_preset',
                'status':'in_progress','namespace':'functions','name':'exec_command',
                'arguments':''}
        emit('response.output_item.added',output_index=index,item=item)
        emit('response.function_call_arguments.delta',item_id=item['id'],output_index=index,delta=arguments)
        emit('response.function_call_arguments.done',item_id=item['id'],output_index=index,
             name='exec_command',arguments=arguments)
        done = dict(item,status='completed',arguments=arguments)
        emit('response.output_item.done',output_index=index,item=done)
        output.append(done)
    else:
        message('PRESET_FIRST_TURN_OK' if stage == 1 else 'PRESET_SECOND_TURN_OK')
    emit('response.completed',response={'id':response_id,'status':'completed','model':model,
         'output':output,'usage':{'input_tokens':20,'output_tokens':10,'total_tokens':30,
         'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}})
    return events
