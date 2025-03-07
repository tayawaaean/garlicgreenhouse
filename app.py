from flask import Flask, render_template, request, redirect, url_for, jsonify, session, Response
import paho.mqtt.publish as mqtt_publish
import paho.mqtt.client as mqtt
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta
from pymongo import MongoClient
from flask_bcrypt import Bcrypt, generate_password_hash, check_password_hash
from bson.json_util import dumps
from bson import ObjectId
import time, os , requests, threading, pytz
from werkzeug.utils import secure_filename
from bson.int64 import Int64 
from functools import wraps
import cv2
from flask_mail import Mail, Message
import random
from flask import flash


app = Flask(__name__)
app.secret_key = 'garlicgreenhouse123'
bcrypt = Bcrypt(app)
serializer = URLSafeTimedSerializer(app.secret_key)

INVITE_CODE = "G49glis12!3#"
ESP32_IP_ADDRESS = "http://10.40.1.21:80"
ESP32_IP_ADDRESS2 = "http://10.40.0.176:80"
esp32_url = "http://192.168.1.63:80" 
ac_ip = "10.40.4.163" 
num_relays = 4
UPLOAD_FOLDER = 'GarlicGreenhouse/static/profilepics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif','jfif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
app.config['MAIL_SERVER'] = 'smtp-mail.outlook.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'iotgarlicgreenhouseg0@outlook.com'  # Update with your Outlook email
app.config['MAIL_PASSWORD'] = 'garlicgreenhouse2023'           # Update with your Outlook password
app.config['MAIL_DEFAULT_SENDER'] = 'iotgarlicgreenhouseg0@outlook.com'  # Update with your Outlook email

mail = Mail(app)

# MQTT broker configuration
mqtt_broker = "broker.hivemq.com"  
temperature_topic = "garlicgreenhouse/temperature"
humidity_topic = "garlicgreenhouse/humidity"
mqttLumens1Topic = "garlicgreenhouse/light1"
mqttLumens2Topic = "garlicgreenhouse/light2"
mqttLumens3Topic = "garlicgreenhouse/light3"
mqttLumens4Topic = "garlicgreenhouse/light4"
current_temperature_topic = "garlicgreenhouse/current_temperature"
LED_CONTROL_TOPIC1 = "garlicgreenhouse/rack1state"
LED_CONTROL_TOPIC2 = "garlicgreenhouse/rack2state"
LED_CONTROL_TOPIC3 = "garlicgreenhouse/rack3state"
LED_CONTROL_TOPIC4 = "garlicgreenhouse/rack4state"
AC_CONTROL_TOPIC ="garlicgreenhouse/ac_state"

# MongoDB configuration
mongo_client = MongoClient("mongodb+srv://iotgarlic:garlicgreenhouse2023@garlicgreenhouse.s6eknyu.mongodb.net")
mongodb_db = mongo_client.GarlicGreenhouse
light_state_collection = mongodb_db.light_state
schedule_collection = mongodb_db.schedule
light_toggle_collection = mongodb_db.light_toggle
ac_control_collection = mongodb_db.ac_control
users_collection = mongodb_db.users
sensor_data_collection = mongodb_db.sensor_data

sensor_data = {
    "temperature": None,
    "humidity": None,
    "lumens1": None,
    "lumens2": None,
    "lumens3": None,
    "lumens4": None,
    "current_temp": None
}

# MQTT client configuration
client = mqtt.Client()
data_lock = threading.Lock()
insert_interval = 300  

# MQTT client configuration
client = mqtt.Client()
manila_timezone = pytz.timezone('Asia/Manila')


import base64

def on_message(client, userdata, message):
    topic = message.topic
    payload = message.payload.decode("utf-8")

    try:
        # Attempt to convert payload to float
        payload = float(payload)
    except ValueError:
        # If conversion fails, payload might be base64 encoded
        try:
            # Attempt to decode payload as base64
            decoded_payload = base64.b64decode(payload).decode("utf-8")
            # Convert decoded payload to float
            payload = float(decoded_payload)
        except Exception as e:
            print("Error decoding payload:", str(e))
            payload = None

    with data_lock:
        if topic == temperature_topic:
            sensor_data["temperature"] = payload
        elif topic == humidity_topic:
            sensor_data["humidity"] = payload
        elif topic == mqttLumens1Topic:
            sensor_data["lumens1"] = payload
        elif topic == mqttLumens2Topic:
            sensor_data["lumens2"] = payload
        elif topic == mqttLumens3Topic:
            sensor_data["lumens3"] = payload
        elif topic == mqttLumens4Topic:
            sensor_data["lumens4"] = payload
        elif topic == current_temperature_topic:
            sensor_data["current_temp"] = payload
        elif topic == AC_CONTROL_TOPIC:
            handle_ac_control(payload) 
        elif topic in [LED_CONTROL_TOPIC1, LED_CONTROL_TOPIC2, LED_CONTROL_TOPIC3, LED_CONTROL_TOPIC4]:
            handle_led_control(topic, payload)

def login_required(route_function):
    @wraps(route_function)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in by verifying if user_id is in session
        if 'user_id' not in session:
            # If the request is JSON, return a JSON response indicating authentication failure
            if request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            # For HTML requests, redirect to the login page
            return redirect(url_for('main_login'))
        # If user is logged in, proceed to the requested route
        return route_function(*args, **kwargs)
    return decorated_function

def handle_ac_control(current_temperature):
    # Make sure the current_temperature is within the desired range
    if 17.0 <= current_temperature <= 30.0:
        # Craft the URL with the ESP32 IP and the current temperature
        url = f"http://{ac_ip}/set?temp={int(current_temperature)}"
        try:
            # Send the HTTP GET request
            response = requests.get(url)
            if response.status_code == 200:
                print("HTTP request sent successfully:", url)
            else:
                print("Failed to send HTTP request:", response.status_code)
        except Exception as e:
            print("Error while sending HTTP request:", str(e))
    else:
        print("Temperature out of range for AC control")

def handle_led_control(topic, payload):
    if payload is not None:
        # Extract relay number from the topic
        relay_num = int(topic.split('/')[-1].replace('rack', '').replace('state', ''))

        # Print the received payload
        print("Received payload:", payload)

        # Convert payload to an integer without decimal point
        payload_int = int(float(payload))

        # Call the appropriate relay control endpoint based on the payload
        esp32_ip_address = ESP32_IP_ADDRESS if relay_num <= 2 else ESP32_IP_ADDRESS2
        if payload_int == 1:
            response = requests.get(f'{esp32_ip_address}/turn_on/{relay_num}')
            if response.status_code == 200:
                return f"Relay {relay_num} turned on successfully"
            else:
                return f"Failed to turn on relay {relay_num}. Status code: {response.status_code}"
        elif payload_int == 0:
            response = requests.get(f'{esp32_ip_address}/turn_off/{relay_num}')
            if response.status_code == 200:
                return f"Relay {relay_num} turned off successfully"
            else:
                return f"Failed to turn off relay {relay_num}. Status code: {response.status_code}"
        else:
            print("Invalid payload for relay control")
            return
    else:
        print("Empty payload received for topic:", topic)

def insert_data_into_mongodb():
    last_inserted_data = None  # Store the last inserted data

    while True:
        time.sleep(insert_interval)
        with data_lock:
            # Check if there is new data
            if any(value is not None for value in sensor_data.values()):
                # Get the current time in Asia/Manila timezone
                current_time_manila = datetime.now(manila_timezone)

                # Format the time and date in 12-hour format
                formatted_time = current_time_manila.strftime('%I:%M:%S %p')
                formatted_date = current_time_manila.strftime('%Y-%m-%d')

                combined_data = {
                    "temperature": sensor_data["temperature"],
                    "humidity": sensor_data["humidity"],
                    "lumens1": sensor_data["lumens1"],
                    "lumens2": sensor_data["lumens2"],
                    "lumens3": sensor_data["lumens3"],
                    "lumens4": sensor_data["lumens4"],
                    "time": formatted_time,
                    "date": formatted_date
                }

                # Insert a single document containing temperature, humidity, and lumens data
                mongodb_db.sensor_data.insert_one(combined_data)

                # Update the last inserted data
                last_inserted_data = combined_data

                print("Data inserted into MongoDB")
            elif last_inserted_data is not None:
                # Insert the last known data if no new data is available
                mongodb_db.sensor_data.insert_one(last_inserted_data)
                print("No new data. Inserting last known data into MongoDB")

# Start the thread for data insertion
insert_thread = threading.Thread(target=insert_data_into_mongodb)
insert_thread.daemon = True
insert_thread.start()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('main_login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes for retrieving sensor data
@app.route('/publish_sensor_data', methods=['GET', 'POST'])
def publish_sensor_data():
    with data_lock:
        # Return the latest sensor data including all lumens topics
        return jsonify({
            "temperature": sensor_data["temperature"],
            "humidity": sensor_data["humidity"],
            "lumens1": sensor_data["lumens1"],
            "lumens2": sensor_data["lumens2"],
            "lumens3": sensor_data["lumens3"],
            "lumens4": sensor_data["lumens4"]
        })

@app.route('/publish-mqtt', methods=['GET'])
def publish_mqtt():
    topic = request.args.get('topic')
    message = request.args.get('message')

    # Publish to MQTT
    client.publish(topic, message)

    return jsonify({'success': True, 'topic': topic, 'message': message})

@app.route('/get_realtime_temperature_data', methods=['GET'])
def get_realtime_temperature_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'temperature': {'$avg': '$temperature'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    temperature_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'temperature': data['temperature'], 'time': data['_id']} for data in temperature_data]

    return jsonify({'temperature_data': formatted_data})

@app.route('/get_realtime_humidity_data', methods=['GET'])
def get_realtime_humidity_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'humidity': {'$avg': '$humidity'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    humidity_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'humidity': data['humidity'], 'time': data['_id']} for data in humidity_data]

    return jsonify({'humidity_data': formatted_data})

@app.route('/get_realtime_lumens1_data', methods=['GET'])
def get_realtime_lumens1_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'lumens1': {'$avg': '$lumens1'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    lumens1_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'lumens1': data['lumens1'], 'time': data['_id']} for data in lumens1_data]

    return jsonify({'lumens1_data': formatted_data})

@app.route('/get_realtime_lumens2_data', methods=['GET'])
def get_realtime_lumens2_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'lumens2': {'$avg': '$lumens2'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    lumens2_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'lumens2': data['lumens2'], 'time': data['_id']} for data in lumens2_data]

    return jsonify({'lumens2_data': formatted_data})

@app.route('/get_realtime_lumens3_data', methods=['GET'])
def get_realtime_lumens3_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'lumens3': {'$avg': '$lumens3'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    lumens3_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'lumens3': data['lumens3'], 'time': data['_id']} for data in lumens3_data]

    return jsonify({'lumens3_data': formatted_data})

@app.route('/get_realtime_lumens4_data', methods=['GET'])
def get_realtime_lumens4_data():
    start_date = request.args.get('start_date')
    selected_datetime = datetime.strptime(start_date, '%Y-%m-%d')

    # Calculate the start and end dates for one day ahead of the selected date
    next_day_start = selected_datetime + timedelta(days=1)
    next_day_end = next_day_start + timedelta(days=1)

    # Define the pipeline for aggregation
    pipeline = [
        {
            '$match': {
                'date': {'$gte': next_day_start.strftime('%Y-%m-%d'), '$lt': next_day_end.strftime('%Y-%m-%d')}
            }
        },
        {
            '$addFields': {
                'time_datetime': {
                    '$toDate': {
                        '$concat': ['$date', ' ', '$time']
                    }
                }
            }
        },
        {
            '$group': {
                '_id': {
                    '$dateToString': {'format': '%Y-%m-%d %H:00:00', 'date': '$time_datetime'}
                },
                'lumens4': {'$avg': '$lumens4'}
            }
        },
        {
            '$sort': {'_id': 1}
        }
    ]

    # Execute the aggregation pipeline
    lumens4_data = list(sensor_data_collection.aggregate(pipeline))

    # Format the result
    formatted_data = [{'lumens4': data['lumens4'], 'time': data['_id']} for data in lumens4_data]

    return jsonify({'lumens4_data': formatted_data})

@app.route('/logout')
def logout():
    return render_template('logout.html')

@app.route('/about')
@login_required
def about():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is not an admin
    if user.get('user_type') == 'Admin':
        return "Unauthorized access. Users only."

    return render_template('about.html', sensor_data=sensor_data, num_relays=num_relays)


@app.route('/alerts')
@login_required
def alerts():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is not an admin
    if user.get('user_type') == 'Admin':
        return "Unauthorized access. Users only."

    # Fetch schedules from MongoDB collection
    schedules = list(schedule_collection.find({}))

    # Pass schedules to the template for rendering
    return render_template('alerts.html', schedules=schedules)


@app.route('/schedule_count')
def get_schedule_count():
    # Count the number of documents in the schedule collection
    schedule_count = schedule_collection.count_documents({})
    return jsonify({'count': schedule_count})

@app.route('/validate_password', methods=['POST'])
def validate_password():
    data = request.json  # Assuming the data is sent in JSON format
    entered_password = data.get('password')  # Extract entered password from JSON

    # Query the database to get the hashed password
    password_document = schedule_collection.find_one({}, {'password': 1})

    if password_document:
        hashed_password = password_document.get('password')

        # Check if the entered password matches the hashed password
        if check_password_hash(hashed_password, entered_password):
            return jsonify({'valid': True}), 200
        else:
            return jsonify({'valid': False}), 401  # Unauthorized
    else:
        return jsonify({'valid': False}), 404  # Not found

@app.route('/delete_all_schedules', methods=['POST'])
def delete_all_schedules():
    # Delete all documents from the schedule collection
    schedule_collection.delete_many({})
    return redirect(url_for('alerts'))

@app.route('/save_alarm', methods=['POST'])
def save_alarm():
    data = request.json  # Assuming the data is sent in JSON format

    # Extracting data from JSON
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    time_on = data.get('time_on')
    time_off = data.get('time_off')
    start_temperature = data.get('start_temperature')  # Extracting start temperature from JSON
    end_temperature = data.get('end_temperature')  # Extracting end temperature from JSON
    password = data.get('password')  # Extracting password from JSON

    # Encrypting password using bcrypt
    hashed_password = generate_password_hash(password).decode('utf-8')

    # Extracting hours and minutes from time_on and time_off
    time_on_hour, time_on_minute = map(int, time_on.split(':'))
    time_off_hour, time_off_minute = map(int, time_off.split(':'))

    # Calculate time_on_start and time_on_end based on saved time_on
    time_on_start = time_on
    time_on_end = time_off

    # Calculate time_off_start and time_off_end based on saved time_off
    if time_off_hour < time_on_hour or (time_off_hour == time_on_hour and time_off_minute <= time_on_minute):
        # If time_off is earlier than or equal to time_on, it crosses midnight
        time_off_start = time_off
        time_off_end = '23:59'
    else:
        # If time_off is later than time_on, it doesn't cross midnight
        time_off_start = f'{time_off_hour:02d}:{time_off_minute+1:02d}' if time_off_minute < 59 else f'{(time_off_hour+1)%24:02d}:00'
        time_off_end = f'{(time_on_hour-1)%24:02d}:{time_on_minute-1:02d}' if time_on_minute > 0 else f'{(time_on_hour-1)%24:02d}:59'

    # Construct document to be inserted into MongoDB
    alarm_doc = {
        'start_date': start_date,
        'end_date': end_date,
        'time_on': time_on,
        'time_off': time_off,
        'start_temperature': start_temperature,  # Include start temperature in the document
        'end_temperature': end_temperature,  # Include end temperature in the document
        'password': hashed_password,  # Include hashed password in the document
        'time_on_start': time_on_start,
        'time_on_end': time_on_end,
        'time_off_start': time_off_start,
        'time_off_end': time_off_end
    }

    # Inserting document into MongoDB collection
    schedule_collection.insert_one(alarm_doc)

    return jsonify({'message': 'Alarm data saved successfully'})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        invite_code = request.form.get('inv_code')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if the invite code is valid
        if invite_code != INVITE_CODE:
            error_message = "Invalid invite code. Please try again."
            return render_template('register.html', error_message=error_message)

        # Check if the email is already registered
        existing_user = mongodb_db.users.find_one({"email": email})
        if existing_user:
            error_message = "Email already registered. Please use a different email."
            return render_template('register.html', error_message=error_message)

        # Hash the password before storing it in the database
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        profpic ="Prof_placeH.webp"

        # Store the user data in MongoDB
        user_data = {
            "name": name,
            "email": email,
            "password": hashed_password,
            "registration_date": datetime.now(),
            "filename_web": profpic
        }
        mongodb_db.users.insert_one(user_data)

        # Redirect to the login page or another relevant page after successful registration
        return redirect(url_for('main_login'))

    # If it's a GET request, render the registration template
    return render_template('register.html')

@app.route('/get_invite_code')
def get_invite_code():
    return jsonify({'invite_code': INVITE_CODE})

@app.route('/users')
@login_required
def users():
    # Assuming you have a MongoDB collection named 'users'
    user = mongodb_db.users.find_one({"email": session.get('email')})
    filename = user.get('filename_web', 'Prof_placeH.webp')  # Get the filename from the user document, or use a default value
    schedules = list(schedule_collection.find({}))
    users = users_collection.find_one({"email": session.get('email')})
    
    return render_template('users.html', 
                           sensor_data=sensor_data, 
                           num_relays=num_relays,
                           filename=filename,
                           schedules=schedules,  
                           current_temperature=current_temperature,
                           users=users)
    pass

@app.route('/upload', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        
        # If the user does not select a file, the browser submits an empty file without a filename
        if file.filename == '':
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Save the uploaded file to the upload folder
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Save the filename in the database
            if 'email' in session:
                email = session['email']
                mongodb_db.users.update_one({"email": email}, {"$set": {"filename_web": filename}})
            
            return 'Image uploaded successfully'
        
@app.route('/update_user', methods=['POST'])
def update_user():
    if 'email' in session:
        email = session['email']
        user = mongodb_db.users.find_one({"email": email})

        if user and bcrypt.check_password_hash(user.get('password', ''), request.form['old_password']):
            # Update user data in the database
            update_data = {"name": request.form['fname'], "email": request.form['email']}

            # Check if the "Change Password" checkbox is selected
            if request.form.get('change_password'):
                old_password = request.form['old_password']
                new_password = request.form['new_password']

                # Verify that the old password matches the one in the database
                if not bcrypt.check_password_hash(user.get('password', ''), old_password):
                    error_message = "Invalid old password. Please try again."
                    return render_template('users.html', error_message=error_message)

                # Hash and update the new password
                update_data['password'] = bcrypt.generate_password_hash(new_password).decode('utf-8')

            mongodb_db.users.update_one({"email": email}, {"$set": update_data})

            # Redirect to the index route on successful update
            return redirect(url_for('main_login'))
        else:
            error_message = "Invalid credentials. Please try again."
            return render_template('users.html', error_message=error_message)
    else:
        # Redirect to the login page if the user is not logged in
        return redirect(url_for('login'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/main_login')
def main_login():
    return render_template('main_login.html') 

@app.route('/otp/<email>', methods=['GET', 'POST'])
def otp(email):
    if request.method == 'POST':
        # Get the OTP submitted by the user
        submitted_otp = request.form['otp']
        
        # Find the user with the provided email
        user = mongodb_db.users.find_one({"email": email})
        
        # Check if the user and OTP exist and match
        if user and 'otp' in user and user['otp'] == submitted_otp:
            # Clear the OTP from the user document
            mongodb_db.users.update_one({"email": email}, {"$unset": {"otp": ""}})
            
            # Proceed to the change_password route and pass the email
            return redirect(url_for('change_password', email=email))
        else:
            # If OTP is incorrect, show an error message
            flash('Invalid OTP. Please try again.', 'error')
            return render_template('otp.html', email=email)
    
    # If it's a GET request, render the OTP verification form
    return render_template('otp.html', email=email)

@app.route('/change_password/<email>')
def change_password(email):
    return render_template('change_password.html', email=email)

@app.route('/update_password', methods=['POST'])
def update_password():
    if request.method == 'POST':
        email = request.form['email']
        new_password = request.form['password']
        confirm_password = request.form['cPassword']
        
        # Check if passwords match
        if new_password != confirm_password:
            flash('Passwords do not match. Please try again.', 'error')
            return redirect(url_for('change_password', email=email))
        
        # Hash the new password
        hashed_password = generate_password_hash(new_password).decode('utf-8')
        
        # Update the password in the database
        mongodb_db.users.update_one({"email": email}, {"$set": {"password": hashed_password}})
        
        # Redirect to a success page or login page
        return redirect(url_for('main_login'))

def generate_otp():
    return str(random.randint(100000, 999999))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        
        # Check if the email exists in the users collection
        user = mongodb_db.users.find_one({"email": email})
        if not user:
            flash('Email not found. Please enter a registered email address.', 'error')
            return render_template('forgot_password.html')
        
        # Generate OTP
        otp = generate_otp()
        
        # Send OTP via email
        msg = Message('Your One-Time Password', recipients=[email])
        msg.body = f'Your OTP is: {otp}'
        mail.send(msg)
        
        # Update user document in the users collection to include OTP
        mongodb_db.users.update_one({"email": email}, {"$set": {"otp": otp}})
        
        # Redirect to OTP page with email as parameter
        return redirect(url_for('otp', email=email))
    
    return render_template('forgot_password.html')

@app.route('/front')
def front():
    return render_template('front.html')    

@app.route('/login', methods=['POST'])
def login():
    # Get email and password from request
    email = request.json.get('email')
    password = request.json.get('password')

    # Find user by email in MongoDB
    user = users_collection.find_one({'email': email})

    if user and bcrypt.check_password_hash(user.get('password', ''), password):
        # Store user ID, email, and userType in the session
        session['user_id'] = str(user.get('_id'))
        session['email'] = email
        session['user_type'] = user.get('user_type')

        return jsonify({'user_type': user.get('user_type')})
    else:
        return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/')
def default():
    # Redirect to the /login route
    return redirect(url_for('main_login'))

@app.route('/turn_on/<int:relay_num>', methods=['GET'])
def turn_on_relay(relay_num):
    # Determine the appropriate IP based on the relay number
    if relay_num in [1, 2]:
        ip_address = '10.40.1.21'
    elif relay_num in [3, 4]:
        ip_address = '10.40.0.176'
    else:
        return f'Relay number {relay_num} is not supported', 400
    
    # Constructing the URL based on the IP and relay_num and sending the HTTP request
    url = f'http://{ip_address}:80/turn_on/{relay_num}'
    response = requests.get(url)
    
    if response.ok:
        # Update the relay state in MongoDB
        light_state_collection.update_one(
            {'relay_num': relay_num},
            {'$set': {'state': True}},
            upsert=True  # Create a new document if it doesn't exist
        )
        
        # Get user's name from the session email
        name = None
        if 'email' in session:
            email = session['email']
            user = users_collection.find_one({'email': email})
            if user:
                name = user.get('name')
        
        # Insert document into light_toggle collection
        light_toggle_collection.insert_one({
            'rack_number': relay_num,
            'action': 'turn_on',
            'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            'controlled_by': name if name else 'Unknown'  # Use user's name or 'Unknown' if not found
        })

        return f'Relay {relay_num} turned on successfully', 200
    else:
        return f'Failed to turn on relay {relay_num}', 500

@app.route('/turn_off/<int:relay_num>', methods=['GET'])
def turn_off_relay(relay_num):
    # Determine the appropriate IP based on the relay number
    if relay_num in [1, 2]:
        ip_address = '10.40.1.21'
    elif relay_num in [3, 4]:
        ip_address = '10.40.0.176'
    else:
        return f'Relay number {relay_num} is not supported', 400
    
    # Constructing the URL based on the IP and relay_num and sending the HTTP request
    url = f'http://{ip_address}:80/turn_off/{relay_num}'
    response = requests.get(url)
    
    if response.ok:
        # Update the relay state in MongoDB
        light_state_collection.update_one(
            {'relay_num': relay_num},
            {'$set': {'state': False}},
            upsert=True  # Create a new document if it doesn't exist
        )
        
        # Get user's name from the session email
        name = None
        if 'email' in session:
            email = session['email']
            user = users_collection.find_one({'email': email})
            if user:
                name = user.get('name')
        
        # Insert document into light_toggle collection
        light_toggle_collection.insert_one({
            'rack_number': relay_num,
            'action': 'turn_off',
            'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            'controlled_by': name if name else 'Unknown'  # Use user's name or 'Unknown' if not found
        })

        return f'Relay {relay_num} turned off successfully', 200
    else:
        return f'Failed to turn off relay {relay_num}', 500
    
# Add this route to your Flask app
@app.route('/get_relay_states', methods=['GET'])
def get_relay_states():
    relay_states = {}  # Initialize an empty dictionary to store relay states

    # Retrieve relay states from MongoDB collection
    light_states = mongodb_db.light_state.find({}, {'_id': 0, 'relay_num': 1, 'state': 1})

    for state in light_states:
        relay_states[state['relay_num']] = state['state']

    return jsonify(relay_states)

    
@app.route("/power")
def toggle_power():
    requests.get(f"{esp32_url}/power")
    return "OK"

@app.route('/set', methods=['GET'])
def set_temperature():
    temp_param = request.args.get('temp')
    new_temperature = float(temp_param)
    update_temperature(new_temperature)
    return 'OK'

def update_temperature(new_temperature):
    global current_temperature

    # Get the current date and time
    current_datetime = datetime.now()

    # Format date and time strings
    formatted_date = current_datetime.strftime('%Y-%m-%d')
    formatted_time = current_datetime.strftime('%I:%M:%S %p')

    # Convert new_temperature to Int32
    new_temperature_int32 = Int64(new_temperature)

    # Save the new temperature in the MongoDB collection
    controlled_by = 'Unknown'
    if 'email' in session:
        email = session['email']
        user = users_collection.find_one({'email': email})
        if user:
            controlled_by = user.get('name')

    # Include controlled_by in temperature_data
    temperature_data = {
        "temperature": new_temperature_int32,
        "date": formatted_date,
        "time": formatted_time,
        "controlled_by": controlled_by
    }

    # Insert the data into the 'ac_control' collection
    mongodb_db.ac_control.insert_one(temperature_data)

    # Query the latest temperature data from the MongoDB collection
    latest_temperature_data = mongodb_db.ac_control.find_one(
        {},
        {"temperature": 1},
        sort=[("date", -1), ("time", -1)]
    )

    # Set current_temperature with the latest value from the collection
    if latest_temperature_data:
        previous_temperature = current_temperature
        current_temperature = latest_temperature_data["temperature"]

        # Update the 'status' field in the 'aircon_tmp' collection
        aircon_tmp_data = {
            "c_temp": current_temperature,
            "status": current_temperature == new_temperature_int32
        }

        # Convert previous_temperature to Int32
        previous_temperature_int32 = Int64(previous_temperature)

        # Insert or update the data in the 'aircon_tmp' collection
        mongodb_db.aircon_tmp.update_one(
            {"c_temp": previous_temperature_int32},
            {"$set": {"status": False}},
        )

        mongodb_db.aircon_tmp.update_one(
            {"c_temp": current_temperature},
            {"$set": aircon_tmp_data},
            upsert=True
        )

    # Send HTTP request to ESP32 to update temperature
    requests.get(f'http://{ac_ip}/set?temp={current_temperature}')


def setup_current_temperature():
    global current_temperature

    # Query the latest temperature data from the MongoDB collection
    latest_temperature_data = mongodb_db.ac_control.find_one(
        {},
        {"temperature": 1},
        sort=[("timestamp", -1)]
    )

    # Set current_temperature with the latest value from the collection
    if latest_temperature_data:
        current_temperature = latest_temperature_data["temperature"]
    else:
        # Set a default value if no temperature data is found
        current_temperature = 17

# Call the setup function at the beginning of your script
setup_current_temperature()

class Camera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        self.lock = threading.Lock()

    def __del__(self):
        self.video.release()

    def get_frame(self):
        with self.lock:
            success, image = self.video.read()
            if not success:
                return None
            _, jpeg = cv2.imencode('.jpg', image)
            return jpeg.tobytes()

@app.route('/video_feed')
def video_feed():
    # Create a new camera instance for each client
    camera = Camera()
    
    def generate_frames(camera):
        while True:
            frame = camera.get_frame()
            if frame is None:
                break
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    
    return Response(generate_frames(camera), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/feed')
@login_required
def feed():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is not an admin
    if user.get('user_type') == 'Admin':
        return "Unauthorized access. Users only."

    return render_template('feed.html')

@app.route('/monitoring')
def monitoring():
    return render_template('monitoring.html')

@app.route('/admin_control')
@login_required
def admin_control():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is an admin
    if user.get('user_type') != 'Admin':
        return "Unauthorized access. Admins only."

    return render_template('admin-control.html')
    pass

@app.route('/admin_dashboard')
def admin_dashboard():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = mongodb_db.users.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Fetch schedule data from MongoDB and sort it
    schedules = list(schedule_collection.find({}))

    return render_template('admin_dashboard.html', 
                           sensor_data=sensor_data, 
                           num_relays=num_relays,
                           schedules=schedules, 
                           current_temperature=current_temperature)

@app.route('/admin_index')
def admin_index():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is an admin
    if user.get('user_type') != 'Admin':
        return "Unauthorized access. Admins only."

    # Fetch schedule data from MongoDB and sort it
    schedules = list(schedule_collection.find({}))

    return render_template('admin_index.html', 
                           sensor_data=sensor_data,  # Ensure these variables are defined or passed appropriately
                           num_relays=num_relays,
                           schedules=schedules, 
                           current_temperature=current_temperature)


@app.route('/admin_users')
@login_required
def admin_users():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is an admin
    if user.get('user_type') != 'Admin':
        return "Unauthorized access. Admins only."

    # Retrieve all users
    users = users_collection.find()
    return render_template('admin-users.html', users=users)
    pass

@app.route('/edit_user', methods=['POST'])
def edit_user():
    user_id = request.form['userId']
    name = request.form['name']
    email = request.form['email']
    position = request.form['position']
    profile = request.form['profile']
    
    # Handle file upload if a new photo is provided
    if 'image' in request.files:
        image = request.files['image']
        if image.filename != '':
            image_path = os.path.join(app.root_path, 'static/profilepics', image.filename)
            image.save(image_path)
            profile = image.filename

    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "name": name,
            "email": email,
            "user_type": position,
            "filename_web": profile
        }}
    )
    
    return redirect(url_for('admin_users'))

@app.route('/delete_user', methods=['POST'])
def delete_user():
    user_id = request.form['userId']
    
    # Assuming users_collection is your MongoDB collection
    users_collection.delete_one({"_id": ObjectId(user_id)})
    
    # Redirect to the page where the user list is displayed after deletion
    return redirect(url_for('admin_users'))

@app.route('/settings')
@login_required
def settings():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is an admin
    if user.get('user_type') != 'Admin':
        return "Unauthorized access. Admins only."

    return render_template('settings.html')


from flask_bcrypt import check_password_hash

@app.route('/delete_all_data', methods=['POST'])
def delete_all_data():
    # Get password and confirm password from the form
    password = request.form['password']
    confirm_password = request.form['confirm-password']

    # Check if password and confirm password match
    if password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match.'}), 400

    # Verify user's password
    user = users_collection.find_one({'email': session.get('email')})
    if user and check_password_hash(user.get('password', ''), password):
        # If password is correct, delete all data from sensor_data collection
        sensor_data_collection.delete_many({})
        return jsonify({'success': True, 'redirect': '/settings', 'message': 'All data deleted successfully.'}), 200
    else:
        return jsonify({'success': False, 'redirect': '/settings', 'message': 'Incorrect password.'}), 401

    # Redirect to settings page after processing the request
    return redirect(url_for('settings'))
@app.route('/control')
@login_required
def control():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is authorized to access the control page
    # Assuming both Admin and User can access this page
    user_type = user.get('user_type')
    if user_type not in ['Admin', 'User']:
        return "Unauthorized access."

    # Fetch schedule data from MongoDB and sort it
    schedule_data = mongodb_db.schedule.find().sort([("monthYearSelected", 1), ("time_start", 1)])
    
    # Convert MongoDB cursor to a list of dictionaries
    schedule_list = [entry for entry in schedule_data]
    
    # Fetch other required data (assuming these variables are defined somewhere in your application)
    schedules = list(schedule_collection.find({}))
    
    # Assuming sensor_data, num_relays, and current_temperature are defined or fetched similarly
    return render_template('control.html', 
                           sensor_data=sensor_data, 
                           num_relays=num_relays,
                           schedule_list=schedule_list,
                           schedules=schedules,  
                           current_temperature=current_temperature)
    pass

@app.route('/latest_controlled_by')
def latest_controlled_by():
    # Fetch the latest entries from the light_toggle collection
    latest_entries = light_toggle_collection.find({}, {'_id': 0, 'rack_number': 1, 'controlled_by': 1})

    # Initialize a dictionary to store controlled_by information for each rack
    controlled_by_dict = {}

    # Iterate over the latest entries and populate the controlled_by_dict
    for entry in latest_entries:
        rack_number = entry.get('rack_number')
        controlled_by = entry.get('controlled_by', 'Unknown')
        controlled_by_dict[rack_number] = controlled_by

    # Return the controlled_by information as JSON
    return jsonify(controlled_by_dict)

@app.route('/latest_ac_control')
def latest_ac_control():
    # Fetch the latest entry from the ac_control collection based on time and date
    latest_entry = ac_control_collection.find_one(sort=[('date', -1), ('time', -1)])

    # Extract the 'controlled_by' field from the latest entry
    controlled_by = latest_entry.get('controlled_by', 'Unknown')

    # Return the controlled_by information as JSON
    return jsonify({'controlled_by': controlled_by})

@app.route('/index')
@login_required
def index():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = users_collection.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Ensure the user is not an admin
    if user.get('user_type') == 'Admin':
        return redirect(url_for('admin_index'))

    # Fetch schedule data from MongoDB and sort it
    schedules = list(schedule_collection.find({}))

    return render_template('index.html', 
                           sensor_data=sensor_data,  # Ensure these variables are defined or passed appropriately
                           num_relays=num_relays,
                           schedules=schedules, 
                           current_temperature=current_temperature)
    pass
    
@app.route('/dashboard')
@login_required
def dashboard():
    # Ensure that the user's email is present in the session
    email = session.get('email')
    if not email:
        # Redirect the user to the login page if the email is not found in the session
        return redirect(url_for('main_login'))

    # Retrieve user data using the email
    user = mongodb_db.users.find_one({"email": email})
    if not user:
        # Handle the case where the user data is not found
        return "User not found. Please log in again."

    # Fetch schedule data from MongoDB and sort it
    schedules = list(schedule_collection.find({}))

    return render_template('dashboard.html', 
                           sensor_data=sensor_data, 
                           num_relays=num_relays,
                           schedules=schedules, 
                           current_temperature=current_temperature)
    pass

if __name__ == '__main__':
    # Connect MQTT client and subscribe to topics
    client.on_message = on_message
    client.connect(mqtt_broker, 1883)
    client.subscribe([
        (temperature_topic, 0),
        (humidity_topic, 0),
        (mqttLumens1Topic, 0),
        (mqttLumens2Topic, 0),
        (mqttLumens3Topic, 0),
        (mqttLumens4Topic, 0),
        (current_temperature_topic, 0),
        (LED_CONTROL_TOPIC1, 0),  # Subscribe to LED control topics
        (LED_CONTROL_TOPIC2, 0),
        (LED_CONTROL_TOPIC3, 0),
        (LED_CONTROL_TOPIC4, 0),
        (AC_CONTROL_TOPIC, 0),
    ])
    client.loop_start()

    # Run the Flask application
    app.run(debug=True, host='0.0.0.0', port=8080)

